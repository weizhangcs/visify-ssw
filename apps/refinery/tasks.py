# 文件路径: apps/refinery/tasks.py

import logging

from celery import shared_task
from django.utils.translation import gettext_lazy as _

from .models import Material
from .services.scheduler import RefineryScheduler

logger = logging.getLogger(__name__)


# 文件路径: apps/refinery/tasks.py


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
        error_msg = _("Probe Failed: %(error)s") % {"error": str(e)}
        _handle_task_error(material_id, error_msg)


# apps/refinery/tasks.py
@shared_task(name="apps.refinery.tasks.refinery_transcode_task", queue="media_queue")
def refinery_transcode_task(material_id: str):
    """
    [原子任务 2] 标准化转码。
    """
    from .services.transcoder import TranscodeService

    try:
        TranscodeService.execute_and_report(material_id)
        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Transcode Error: {str(e)}")


@shared_task(name="apps.refinery.tasks.refinery_slice_task", queue="media_queue")
def refinery_slice_task(material_id: str):
    """
    [原子任务 3] 视觉切片。
    """
    try:
        material = Material.objects.get(id=material_id)
        # 模拟切片产出
        material.visual_slices = [{"id": 1, "start": 0, "end": 10}]
        material.save(update_fields=["visual_slices", "modified"])
        RefineryScheduler.schedule(material_id)
    except Exception as e:
        _handle_task_error(material_id, f"Slice Error: {str(e)}")


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
