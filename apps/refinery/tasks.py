import logging
from pathlib import Path

from celery import shared_task

from .models import Material

logger = logging.getLogger(__name__)


@shared_task(name="apps.refinery.tasks.refinery_transcode_task", queue="media_queue")
def refinery_transcode_task(material_id: str):
    """
    [原子任务] 转码服务
    范式：Task 决定物理路径 -> Service 执行 -> Context 记录契约
    """
    from .services.context import RefineryContext
    from .services.scheduler import RefineryScheduler
    from .services.transcoder import TranscodeService

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 物理终点决策：直接在 media_dir 下建立 proxy 子目录
            rel_proxy_dir = Path("proxy") / str(material_id)
            abs_proxy_dir = ctx.media_dir / rel_proxy_dir
            abs_proxy_dir.mkdir(parents=True, exist_ok=True)

            abs_proxy_path = abs_proxy_dir / "proxy.mp4"

            # 2. 执行物理算子（直接写入终点，绕过 work_dir 搬运）
            TranscodeService.run(ctx.source_video_path, abs_proxy_path)

            # 3. Context 提交物理路径契约
            ctx.commit_transcode_status(str(rel_proxy_dir / "proxy.mp4"))

        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Transcode Stage Failed: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_probe_task", queue="media_queue")
def refinery_probe_task(material_id: str):
    """
    [原子任务] 元数据与声纹探测
    范式：利用 ctx.work_dir 处理中间计算产生的临时文件
    """
    from .services.context import RefineryContext
    from .services.probe import ProbeService
    from .services.scheduler import RefineryScheduler

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 隔离的临时工作文件
            temp_wav_path = ctx.work_dir / "audio_sample.wav"

            # 2. 基于 Proxy 基准执行探测
            tech_meta, duration, waveform = ProbeService.run(ctx.proxy_video_path, temp_wav_path)

            # 3. 提交结构化结果
            ctx.commit_probe_results(tech_meta, duration, waveform)

        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Probe Stage Failed: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_hls_task", queue="media_queue")
def refinery_hls_task(material_id: str):
    """
    [原子任务] HLS 切片
    范式：Service 直接向正式产出目录写入大量零碎文件
    """
    from .services.context import RefineryContext
    from .services.hls_generator import HLSService
    from .services.scheduler import RefineryScheduler

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 物理终点决策
            rel_hls_dir = Path("hls") / str(material_id)
            abs_hls_dir = ctx.media_dir / rel_hls_dir

            # 2. 执行物理算子（直接写入 media_dir）
            HLSService.run(ctx.proxy_video_path, abs_hls_dir)

            # 3. 提交索引文件的相对路径
            ctx.commit_hls_status(str(rel_hls_dir / "index.m3u8"))

        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"HLS Stage Failed: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_analyze_text_task", queue="media_queue")
def refinery_analyze_text_task(material_id: str):
    """
    [原子任务] 文本结构化解析
    """
    from .services.context import RefineryContext
    from .services.scheduler import RefineryScheduler
    from .services.text_analyzer import TextAnalyzerService

    try:
        with RefineryContext(material_id) as ctx:
            content = ctx.source_subtitle_content

            # 执行解析并提交（逻辑保持简洁）
            dialogue_list = TextAnalyzerService.run(content) if content else []
            ctx.commit_analysis_results(dialogue_list)

        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Text Analyzing Stage Failed: {str(e)}")


def _handle_task_error(material_id: str, error_msg: str):
    """统一 FSM 失败处理"""
    logger.error(f"[Refinery Task Failure] {material_id}: {error_msg}")
    try:
        material = Material.objects.get(id=material_id)
        material.handle_failure(str(error_msg))
        material.save(update_fields=["status", "error_log", "modified"])
    except Material.DoesNotExist:
        logger.error(f"Cannot log error: Material {material_id} not found.")


@shared_task(name="apps.refinery.tasks.refinery_slicing_task", queue="media_queue")
def refinery_slicing_task(material_id: str):
    """
    [原子任务] 视觉切片
    范式：从 Context 获取 Proxy 路径及对白数据 -> Service 计算 -> Context 存回 JSONB
    """
    from .services.context import RefineryContext
    from .services.scheduler import RefineryScheduler
    from .services.slicer import SlicingService

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 调用纯算子 (完全基于 Context 提供的真值)
            slices_manifest = SlicingService.run(
                video_path=ctx.proxy_video_path, video_duration=ctx.duration, dialogue_track=ctx.dialogue_track
            )

            # 2. 提交计算结果
            ctx.commit_slicing_results(slices_manifest)

        # 3. 调度
        RefineryScheduler.schedule(material_id)

    except Exception as e:
        _handle_task_error(material_id, f"Slicing Stage Failed: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_frame_extract_task", queue="media_queue")
def refinery_frame_extract_task(material_id: str):
    """
    [原子任务] 关键帧提取
    范式：决策 media_dir/frames 终点 -> Service 并行抽帧 -> Context 回填 JSONB
    """
    from .services.context import RefineryContext
    from .services.frame_extractor import FrameExtractorService
    from .services.scheduler import RefineryScheduler

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 物理终点决策 (对齐 media_dir 规范)
            rel_frames_dir = Path("frames") / str(material_id)
            abs_frames_dir = ctx.media_dir / rel_frames_dir

            # 2. 调用物理算子
            # 传入 proxy_video_path (真值) 和 物理/业务相对路径
            updated_slices = FrameExtractorService.run(
                video_path=ctx.proxy_video_path,
                slices=ctx.visual_slices,
                abs_output_dir=abs_frames_dir,
                rel_output_dir=rel_frames_dir,
            )

            # 3. 提交结果
            ctx.commit_extracted_frames(updated_slices)

        # 4. 调度
        RefineryScheduler.schedule(material_id)

    except Exception as e:
        _handle_task_error(material_id, f"Frame Extraction Failed: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_sync_task", queue="media_queue")
def refinery_sync_task(material_id: str):
    """
    [原子任务] 帧数据同步
    范式：SyncContext 准备路径与配置 -> TicketUploader 执行搬运 -> Context 回填 GS 路径
    """
    from .services.context import RefineryContext
    from .services.scheduler import RefineryScheduler
    from .services.uploader import TicketUploader

    try:
        with RefineryContext(material_id) as ctx:
            # 1. 提取物理清单
            files_to_sync = ctx.frame_paths_manifest
            if not files_to_sync:
                logger.info(f"Sync Task: No frames to upload for {material_id}. Skipping.")
                ctx.material.finish_current_task()  # 即使没图也要闭环状态机
                ctx.material.save()
                return

            # 2. 调用搬运算子 (注入 Context 提供的配置和伪装 ID)
            uploader = TicketUploader(
                material_id=str(ctx.material_id),  # 伪装为 media_id
                asset_id=str(ctx.material.media.asset_id),
                cloud_client=ctx.cloud_client,
            )

            # 这里会看到你想要的 Batch 和 Progress 日志
            cloud_mapping = uploader.upload_files(files_to_sync)

            # 3. 数据回填 (Remapping)
            ctx.commit_sync_results(cloud_mapping)

        # 4. 触发调度逻辑 (如通知云端或进入下一个状态)
        RefineryScheduler.schedule(material_id)

    except Exception as e:
        _handle_task_error(material_id, f"Sync Stage Failed: {str(e)}")
