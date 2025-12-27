# 文件路径: apps/refinery/tasks.py

import logging

from celery import shared_task

from .models import Material
from .services.scheduler import RefineryScheduler

logger = logging.getLogger(__name__)


@shared_task(name="apps.refinery.tasks.refinery_probe_task", queue="media_queue")
def refinery_probe_task(material_id: str):
    """
    [原子任务 1] 获取视频的技术元数据。
    """
    from .services.probe import ProbeService

    try:
        ProbeService.execute_and_report(material_id)
        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Media probing Error: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_analyze_text_task", queue="media_queue")
def refinery_analyze_text_task(material_id: str):
    """
    [原子任务] 文本结构化处理
    """
    from .services.text_analyzer import TextAnalyzerService

    try:
        TextAnalyzerService.execute_and_report(material_id)
        # 任务完成后呼叫调度器进入下一阶段
        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Text Analysis Error: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_transcode_task", queue="media_queue")
def refinery_transcode_task(material_id: str):
    """
    [原子任务] 转码
    """
    from .services.transcoder import TranscodeService

    try:
        TranscodeService.execute_and_report(material_id)
        # 任务完成后呼叫调度器进入下一阶段
        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Transcode Error: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_hls_task", queue="media_queue")
def refinery_hls_task(material_id: str):
    """
    [原子任务] HLS切片服务
    """
    from .services.hls_generator import HLSService

    try:
        HLSService.execute_and_report(material_id)
        # 任务完成后呼叫调度器进入下一阶段
        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"HLS generator Error: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_slicing_task", queue="media_queue")
def refinery_slicing_task(material_id: str):
    """
    [原子任务] 经典CV算法进行切片
    """
    from .services.slicer import SlicingService

    try:
        SlicingService.execute_and_report(material_id)
        # 任务完成后呼叫调度器进入下一阶段
        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Slicing Error: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_extractframe_task", queue="media_queue")
def refinery_frame_extracting_task(material_id: str):
    """
    [原子任务] 抽取首中尾帧
    """
    from .services.frame_extractor import FrameExtractorService

    try:
        FrameExtractorService.execute_and_report(material_id)
        # 任务完成后呼叫调度器进入下一阶段
        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Frame Extracting Error: {str(e)}")


def _handle_task_error(material_id: str, error_msg: str):
    """私有方法：通过合法 Transition 统一处理精炼厂内的任务失败"""
    logger.error(f"[Refinery Task Failure] {material_id}: {error_msg}")

    # 获取实例并调用 transition 方法，严禁直接 update 状态字段
    try:
        material = Material.objects.get(id=material_id)
        material.handle_failure(str(error_msg))  # 调用 models.py 中定义的 handle_failure
        material.save(update_fields=["status", "error_log", "modified"])
    except Material.DoesNotExist:
        logger.error(f"Cannot log error: Material {material_id} not found.")
