# apps/workflow/transcoding/tasks.py

import json
import logging
import os
import shutil  # [新增] 用于清理文件夹
import subprocess
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from apps.media_assets.models import Media

# [新增] 引入存储服务
from apps.media_assets.services.storage import StorageService
from apps.workflow.models import TranscodingJob, TranscodingProject

from .utils import generate_peaks_from_video

logger = logging.getLogger(__name__)


def _check_and_update_project_status(project: TranscodingProject):
    """
    检查给定项目下的所有转码任务状态，并更新项目的聚合状态。
    """
    project.refresh_from_db()
    all_jobs = project.transcoding_jobs.all()

    if all_jobs.count() == 0:
        return

    failed_exists = all_jobs.filter(status="ERROR").exists()
    running_exists = all_jobs.filter(status__in=["PENDING", "PROCESSING", "CREATED"]).exists()

    new_status = project.status

    if failed_exists:
        new_status = "FAILED"
    elif not running_exists:
        new_status = "COMPLETED"
    else:
        return

    if project.status != new_status:
        project.status = new_status
        project.save(update_fields=["status"])
        logger.info(f"Project {project.id} status updated to {new_status}")


@shared_task(name="apps.workflow.transcoding.tasks.generate_waveform")
def generate_waveform_task(media_id):
    """
    独立任务：为指定 Media 生成波形数据
    """
    logger.info(f"Starting waveform generation for Media {media_id}")
    try:
        media = Media.objects.get(id=media_id)
        if not media.source_video:
            logger.warning(f"Media {media_id} has no source video, skipping waveform.")
            return

        temp_dir = Path(settings.MEDIA_ROOT) / "temp_waveforms"
        temp_dir.mkdir(parents=True, exist_ok=True)

        json_filename = f"waveform_{media.id}.json"
        temp_json_path = temp_dir / json_filename

        success = generate_peaks_from_video(media.source_video.path, temp_json_path)

        if success and temp_json_path.exists():
            with open(temp_json_path, "rb") as f:
                media.waveform_data.save(json_filename, ContentFile(f.read()), save=True)
            logger.info(f"Waveform generated and saved for Media {media_id}")
            os.remove(temp_json_path)
        else:
            logger.error(f"Failed to generate waveform for Media {media_id}")
    except Exception as e:
        logger.error(f"Error in generate_waveform_task: {e}", exc_info=True)


@shared_task(name="apps.workflow.transcoding.tasks.run_transcoding_job")
def run_transcoding_job(job_id):
    """
    (V5.4 Proxy First Strategy)
    1. FFmpeg: Source -> Proxy MP4 (720p)
    2. FFprobe: 获取时长
    3. FFmpeg: Proxy MP4 -> HLS (copy stream, fast slice)
    4. Storage: 上传 Proxy 和 HLS
    """
    try:
        job = TranscodingJob.objects.select_related("project", "profile", "media__asset").get(id=job_id)
    except TranscodingJob.DoesNotExist:
        return

    if job.status == "PENDING":
        job.start()
        job.save()

    media = job.media
    if not media.source_video:
        job.fail()
        job.save()
        return

    # --- 目录准备 ---
    source_path = Path(media.source_video.path)
    work_dir = Path(settings.MEDIA_ROOT) / "temp_transcoding" / str(job.id)
    work_dir.mkdir(parents=True, exist_ok=True)

    proxy_mp4_path = work_dir / "proxy.mp4"
    hls_dir = work_dir / "hls"
    hls_dir.mkdir(exist_ok=True)
    hls_index_path = hls_dir / "index.m3u8"

    try:
        # === Step 1: 生成 Proxy MP4 (重算力) ===
        # 使用 Profile 中定义的命令，但强制输出到 proxy.mp4
        encoding_params = job.profile.ffmpeg_command.split()

        # 确保 Profile 里没有 -f hls 等参数，如果用户手误配置了，这里可能要清洗参数
        # 简单起见，我们假设 Profile 已经是干净的 MP4 转码参数
        cmd_proxy = ["ffmpeg", "-i", str(source_path), *encoding_params, str(proxy_mp4_path), "-y"]

        logger.info(f"Step 1 Transcode: {' '.join(cmd_proxy)}")
        subprocess.run(cmd_proxy, check=True, capture_output=True, text=True, encoding="utf-8")

        # === Step 2: 获取时长 (基于 Proxy) ===
        try:
            probe_cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(proxy_mp4_path)]
            result = subprocess.run(probe_cmd, check=True, capture_output=True, text=True)
            meta = json.loads(result.stdout)
            duration = float(meta["format"]["duration"])

            if abs(media.duration - duration) > 0.1:
                media.duration = duration
                media.save(update_fields=["duration"])
        except Exception as e:
            logger.warning(f"Probe failed: {e}")

        # === Step 3: HLS 切片 (轻量级) ===
        # 直接对 Proxy MP4 进行切片 (copy codec)
        # -hls_list_size 0: 保留所有切片
        # -hls_time 10: 10秒一个切片
        cmd_hls = [
            "ffmpeg",
            "-i",
            str(proxy_mp4_path),
            "-c",
            "copy",  # 关键：直接复制流，不重编码，速度极快
            "-f",
            "hls",
            "-hls_time",
            "10",
            "-hls_list_size",
            "0",
            str(hls_index_path),
        ]
        logger.info(f"Step 2 HLS Slice: {' '.join(cmd_hls)}")
        subprocess.run(cmd_hls, check=True, capture_output=True, text=True, encoding="utf-8")

        # === Step 4: 存储与交付 (Update V5.5) ===
        storage = StorageService()

        # 获取包含双路径的结果字典
        result_map = storage.save_proxy_and_hls(proxy_mp4_path, hls_dir, job)

        # [核心变更] 分别存储
        # 1. output_url -> HLS 播放地址 (给前端 VideoPlayer 用)
        job.output_url = result_map["hls_url"]

        # 2. output_file -> Proxy MP4 物理路径 (给后续 Slicing 算法用)
        # 这样做还有一个好处：在 Django Admin 点击这个文件，下载的是 MP4，方便人工检查画质
        job.output_file.name = result_map["proxy_file_path"]

        job.complete()
        job.save()

        # 触发波形
        if not media.waveform_data:
            transaction.on_commit(lambda: generate_waveform_task.delay(media.id))

        logger.info(f"Job {job_id} Done. HLS: {job.output_url}, Proxy: {job.output_file.name}")

    except Exception as e:
        logger.error(f"Transcoding Failed: {e}", exc_info=True)
        job.fail()
        job.save()
        raise e
    finally:
        # 清理工作目录
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
