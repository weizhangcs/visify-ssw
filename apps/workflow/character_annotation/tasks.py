# 文件路径: apps/workflow/character_annotation/tasks.py

import json
import logging
import os
import tempfile
from pathlib import Path

from celery import shared_task
from django.core.files.base import ContentFile

from apps.workflow.common.cloud_client import CloudApiService

from .models import CharacterAnnotationProject
from .services.srt_processor import SRTBatchProcessor

logger = logging.getLogger(__name__)


@shared_task(name="apps.workflow.character_annotation.tasks.start_character_annotation_task")
def start_character_annotation_task(project_id: str):
    """
    [Initiator] 启动任务
    """
    try:
        project = CharacterAnnotationProject.objects.get(id=project_id)
    except CharacterAnnotationProject.DoesNotExist:
        logger.error(f"Project {project_id} not found")
        return

    # 1. 状态初始化
    project.status = "PROCESSING"
    project.save()

    jobs = project.jobs.filter(status="PENDING")
    if not jobs.exists():
        logger.warning(f"No pending jobs for project {project_id}")
        return

    for job in jobs:
        job.start()
        job.save()

    cloud = CloudApiService()
    processor = SRTBatchProcessor()

    try:
        # 2. 准备数据并合并 SRT
        srt_inputs = []
        for job in jobs:
            if job.media.source_subtitle:
                with job.media.source_subtitle.open("r") as f:
                    content = f.read()
                    if isinstance(content, bytes):
                        content = content.decode("utf-8", errors="ignore")
                    srt_inputs.append({"media_id": str(job.media.id), "content": content})

        if not srt_inputs:
            raise ValueError("No valid source subtitles found in jobs")

        merged_srt_text = processor.merge_srts(srt_inputs)

        # 写入临时文件上传
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".srt", delete=False, encoding="utf-8") as tmp:
            tmp.write(merged_srt_text)
            tmp_path = Path(tmp.name)

        success, upload_result = cloud.upload_file(tmp_path)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        if not success:
            raise RuntimeError(f"Cloud upload failed: {upload_result}")

        # 3. 提交任务
        payload = {
            "subtitle_path": upload_result,
            "known_characters": project.override_characters or [],
            "video_title": project.name,
            "model_name": "gemini-2.5-flash",
            "lang": project.asset.language.split("-")[0] if project.asset.language else "zh",
        }

        api_success, task_response = cloud.create_task("character_pre_annotator", payload)

        if not api_success:
            raise RuntimeError(f"Cloud API submission failed: {task_response}")

        cloud_task_id = task_response.get("id")

        # 4. 更新 Job 追踪 ID
        jobs.update(cloud_task_id=cloud_task_id)

        # 5. 启动轮询器 (调用新的公共总线)
        # 找到 start_character_annotation_task 的第 5 步：
        from apps.workflow.common.tasks import poll_cloud_task_general

        poll_cloud_task_general.delay(
            model_name="CharacterAnnotationProject",  # 直接告诉轮询器 model 名字
            job_id=str(project.id),
            cloud_task_id=cloud_task_id,
            on_complete_task_name="apps.workflow.character_annotation.tasks.finalize_character_annotation_task",
            on_complete_kwargs={},
        )

    except Exception as e:
        logger.exception(f"Start task failed for project {project_id}")
        project.status = "FAILED"
        project.save()
        for job in project.jobs.filter(status="PROCESSING"):
            job.fail()
            job.error_message = str(e)
            job.save()


@shared_task(name="apps.workflow.character_annotation.tasks.finalize_character_annotation_task")
def finalize_character_annotation_task(job_id: str, cloud_task_data: dict, **kwargs):
    """
    [Callback] 完成任务回调
    """
    try:
        project = CharacterAnnotationProject.objects.get(id=job_id)
        jobs = project.jobs.filter(status="PROCESSING")
    except CharacterAnnotationProject.DoesNotExist:
        return

    cloud = CloudApiService()
    processor = SRTBatchProcessor()

    try:
        # 1. 下载识别结果
        result_url = cloud_task_data.get("download_url") or cloud_task_data.get("result", {}).get("download_url")
        if not result_url:
            raise ValueError("No download URL found in task response")

        success, content = cloud.download_task_result(result_url)
        if not success:
            raise RuntimeError("Failed to download result")

        result_json = json.loads(content)

        # 2. 重建处理器内部映射
        rebuild_inputs = []
        for job in jobs:
            if job.media.source_subtitle:
                with job.media.source_subtitle.open("r") as f:
                    content_str = f.read()
                    if isinstance(content_str, bytes):
                        content_str = content_str.decode("utf-8", errors="ignore")
                    rebuild_inputs.append({"media_id": str(job.media.id), "content": content_str})

        processor.merge_srts(rebuild_inputs)

        # 3. 结果分发
        ass_results_map = processor.generate_ass_files(result_json)
        roster_stats = result_json.get("character_roster", [])

        for job in jobs:
            media_id = str(job.media.id)
            ass_content = ass_results_map.get(media_id)

            if ass_content:
                job.character_stats = {"roster": roster_stats}
                file_name = f"{job.media.title}_ai.ass"
                job.output_ass_file.save(file_name, ContentFile(ass_content.encode("utf-8")), save=False)

            job.complete()
            job.save()

        project.status = "COMPLETED"
        project.save()

    except Exception as e:
        logger.exception(f"Finalize failed for project {job_id}")
        project.status = "FAILED"
        project.save()
        jobs.update(status="ERROR", error_message=str(e))
