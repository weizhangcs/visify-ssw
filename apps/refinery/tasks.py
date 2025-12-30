# 文件路径: apps/refinery/tasks.py
import logging
import time
from pathlib import Path

from celery import shared_task

from .models import Material

logger = logging.getLogger(__name__)


def _handle_task_success(material_id: str, slug: str, start_time: float):
    """
    [增强型成功回调]
    职责：计算耗时并回流给 Scheduler 进行指标记录与下一步决策。
    """
    from .services.scheduler import RefineryScheduler

    duration = round(time.time() - start_time, 2)
    logger.info(f"✅ 原子单元 [{slug}] 执行成功 (Material: {material_id}), 耗时: {duration}s")

    # 调用增强后的调度器，记录指标并驱动管线
    RefineryScheduler.record_and_schedule(material_id, slug, duration)


def _handle_task_error(material_id: str, slug: str, error_msg: str):
    """
    [标准化失败处理]
    职责：标记 FSM 失败状态，并将带步骤上下文的错误日志写入数据库，使 View 可见。
    """
    logger.error(f"❌ 原子单元 [{slug}] 执行失败 (Material: {material_id}): {error_msg}")
    try:
        material = Material.objects.get(id=material_id)
        # 调用模型 transition 标记失败，并持久化错误日志
        material.handle_failure(f"[{slug}] {str(error_msg)}")
        material.save(update_fields=["status", "error_log", "modified"])
    except Material.DoesNotExist:
        logger.error(f"Cannot log error: Material {material_id} not found.")


# ==============================================================================
# 原子任务单元 (Atomic Task Units)
# ==============================================================================


@shared_task(name="apps.refinery.tasks.refinery_transcode_task", queue="media_queue")
def refinery_transcode_task(material_id: str):
    """
    [原子任务 1] 标准化转码 (720p Proxy)
    """
    from .services.context import RefineryContext
    from .services.transcoder import TranscodeService

    start_time = time.time()
    slug = "transcode"

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 物理终点决策
            rel_proxy_dir = Path("proxy") / str(material_id)
            abs_proxy_dir = ctx.media_dir / rel_proxy_dir
            abs_proxy_dir.mkdir(parents=True, exist_ok=True)
            abs_proxy_path = abs_proxy_dir / "proxy.mp4"

            # 2. 执行物理算子
            TranscodeService.run(ctx.source_video_path, abs_proxy_path)

            # 3. Context 提交物理路径契约
            ctx.commit_transcode_status(str(rel_proxy_dir / "proxy.mp4"))

        _handle_task_success(material_id, slug, start_time)
    except Exception as e:
        _handle_task_error(material_id, slug, str(e))


@shared_task(name="apps.refinery.tasks.refinery_probe_task", queue="media_queue")
def refinery_probe_task(material_id: str):
    """
    [原子任务 2] 元数据与声纹探测
    """
    from .services.context import RefineryContext
    from .services.probe import ProbeService

    start_time = time.time()
    slug = "probe"

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 基于 Proxy 基准执行探测，使用临时工作目录处理音频中间件
            temp_wav_path = ctx.work_dir / "audio_sample.wav"
            tech_meta, duration, waveform = ProbeService.run(ctx.proxy_video_path, temp_wav_path)

            # 2. 提交结构化结果
            ctx.commit_probe_results(tech_meta, duration, waveform)

        _handle_task_success(material_id, slug, start_time)
    except Exception as e:
        _handle_task_error(material_id, slug, str(e))


@shared_task(name="apps.refinery.tasks.refinery_analyze_text_task", queue="media_queue")
def refinery_analyze_text_task(material_id: str):
    """
    [原子任务 3] 文本结构化解析 (SRT -> JSONB)
    """
    from .services.context import RefineryContext
    from .services.text_analyzer import TextAnalyzerService

    start_time = time.time()
    slug = "analyze_text"

    try:
        with RefineryContext(material_id) as ctx:
            content = ctx.source_subtitle_content
            # 执行解析（如果内容为空则返回空列表）
            dialogue_list = TextAnalyzerService.run(content) if content else []
            ctx.commit_analysis_results(dialogue_list)

        _handle_task_success(material_id, slug, start_time)
    except Exception as e:
        _handle_task_error(material_id, slug, str(e))


@shared_task(name="apps.refinery.tasks.refinery_hls_task", queue="media_queue")
def refinery_hls_task(material_id: str):
    """
    [原子任务 4] HLS 标准切片 (用于前端流媒体预览)
    """
    from .services.context import RefineryContext
    from .services.hls_generator import HLSService

    start_time = time.time()
    slug = "hls"

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 物理终点决策
            rel_hls_dir = Path("hls") / str(material_id)
            abs_hls_dir = ctx.media_dir / rel_hls_dir

            # 2. 执行物理算子
            HLSService.run(ctx.proxy_video_path, abs_hls_dir)

            # 3. 提交索引文件的相对路径
            ctx.commit_hls_status(str(rel_hls_dir / "index.m3u8"))

        _handle_task_success(material_id, slug, start_time)
    except Exception as e:
        _handle_task_error(material_id, slug, str(e))


@shared_task(name="apps.refinery.tasks.refinery_slicing_task", queue="media_queue")
def refinery_slicing_task(material_id: str):
    """
    [原子任务 5] 视觉智能切片
    """
    from .services.context import RefineryContext
    from .services.slicer import SlicingService

    start_time = time.time()
    slug = "slicing"

    try:
        with RefineryContext(material_id) as ctx:
            # 基于 Context 提供的真值执行纯算子计算
            slices_manifest = SlicingService.run(
                video_path=ctx.proxy_video_path, video_duration=ctx.duration, dialogue_track=ctx.dialogue_track
            )
            # 提交计算结果到 JSONB 字段
            ctx.commit_slicing_results(slices_manifest)

        _handle_task_success(material_id, slug, start_time)
    except Exception as e:
        _handle_task_error(material_id, slug, str(e))


@shared_task(name="apps.refinery.tasks.refinery_frame_extract_task", queue="media_queue")
def refinery_frame_extract_task(material_id: str):
    """
    [原子任务 6] 关键帧提取 (大规模并行抽帧)
    """
    from .services.context import RefineryContext
    from .services.frame_extractor import FrameExtractorService

    start_time = time.time()
    slug = "frame_extract"

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 物理终点决策
            rel_frames_dir = Path("frames") / str(material_id)
            abs_frames_dir = ctx.media_dir / rel_frames_dir

            # 2. 并行抽帧，回填本地相对路径到 visual_slices 结构中
            updated_slices = FrameExtractorService.run(
                video_path=ctx.proxy_video_path,
                slices=ctx.visual_slices,
                abs_output_dir=abs_frames_dir,
                rel_output_dir=rel_frames_dir,
            )

            # 3. 提交结果
            ctx.commit_extracted_frames(updated_slices)

        _handle_task_success(material_id, slug, start_time)
    except Exception as e:
        _handle_task_error(material_id, slug, str(e))


@shared_task(name="apps.refinery.tasks.refinery_sync_task", queue="media_queue")
def refinery_sync_task(material_id: str):
    """
    [原子任务 7] 帧数据同步 (本地 -> 云端 GCS/S3)
    """
    from .services.context import RefineryContext
    from .services.uploader import TicketUploader

    start_time = time.time()
    slug = "sync"

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 提取物理待上传清单
            files_to_sync = ctx.frame_paths_manifest
            if not files_to_sync:
                logger.info(f"Sync Task: No frames to upload for {material_id}. Skipping.")
                _handle_task_success(material_id, slug, start_time)
                return

            # 2. 调用搬运算子 (注入数据库配置)
            uploader = TicketUploader(
                material_id=str(ctx.material_id),
                asset_id=str(ctx.material.media.asset_id),
                cloud_client=ctx.cloud_client,
            )

            # 执行分批次换票上传
            cloud_mapping = uploader.upload_files(files_to_sync)

            # 3. 数据路径映射回填 (Local Path -> GS URI)
            ctx.commit_sync_results(cloud_mapping)

        _handle_task_success(material_id, slug, start_time)
    except Exception as e:
        _handle_task_error(material_id, slug, str(e))


@shared_task(name="apps.refinery.tasks.refinery_character_recognition_task", queue="media_queue")
def refinery_character_recognition_task(material_id: str):
    from apps.workflow.common.cloud_client import CloudApiService

    from .services.character_refiner import CharacterRefinerService
    from .services.context import RefineryContext

    start_time = time.time()
    slug = "character_recognition"
    cloud_client = CloudApiService()

    try:
        with RefineryContext(material_id) as ctx:
            # 1. Context 负责准备物理参数
            # 1. Context 负责准备物理路径和元数据
            local_json_path = ctx.prepare_dialogue_json()
            asset_meta = ctx.get_asset_metadata_for_refiner()

            # 2. Service 仅作为纯粹的算子执行，不持有 ctx 对象
            result_data = CharacterRefinerService.run(
                client=cloud_client, local_json_path=local_json_path, asset_meta=asset_meta
            )

            # 3. Context 负责将数据持久化
            ctx.apply_character_recognition_results(result_data)

        # 成功回流指标
        _handle_task_success(material_id, slug, start_time)

    except Exception as e:
        _handle_task_error(material_id, slug, str(e))
