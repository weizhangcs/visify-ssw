# 文件路径: apps/workflow/common/tasks.py

import logging

from celery import shared_task
from django.apps import apps

from apps.common.cloud_client import CloudApiService
from visify_ssw.celery import app as celery_app

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="apps.workflow.common.tasks.poll_cloud_task", max_retries=100, default_retry_delay=30)
def poll_cloud_task(self, job_id, cloud_task_id, on_complete_task_name, on_complete_kwargs, model_name=None):
    """
    (V2.0 - 公共组件) 通用云端任务轮询器。

    统一接管 InferenceJob 和 CreativeJob 的轮询工作。
    支持显式指定 model_name，也保留了基于回调任务名的智能推断逻辑以兼容旧代码。
    """
    # 1. 确定模型类
    if not model_name:
        # 智能兼容逻辑：根据回调任务名推断
        if "creative" in on_complete_task_name:
            model_name = "CreativeJob"
        else:
            model_name = "InferenceJob"

    try:
        # 始终使用 "workflow" label，因为所有业务模型都在这个 App 下
        JobModel = apps.get_model("workflow", model_name)
        job = JobModel.objects.get(id=job_id)
    except LookupError:
        logger.error(f"[PollTask] 无法加载模型 workflow.{model_name}。")
        return
    except JobModel.DoesNotExist:
        logger.error(f"[PollTask] 找不到 {model_name} (ID: {job_id})。")
        return

    # 2. 查询云端状态
    service = CloudApiService()
    try:
        success, data = service.get_task_status(cloud_task_id)
    except Exception as e:
        logger.error(f"[PollTask] API查询异常 (Job: {job_id}): {e}", exc_info=True)
        self.retry()
        return

    if not success:
        logger.warning(f"[PollTask] 查询失败 (Job: {job_id})，将在 {self.default_retry_delay}s 后重试。")
        self.retry()
        return

    status = data.get("status")

    # 3. 状态分发
    if status == "COMPLETED":
        logger.info(f"[PollTask] 云端任务 {cloud_task_id} 完成。触发回调: {on_complete_task_name}")
        celery_app.send_task(
            on_complete_task_name, kwargs={"job_id": str(job_id), "cloud_task_data": data, **on_complete_kwargs}
        )

    elif status in ["PENDING", "RUNNING"]:
        logger.info(f"[PollTask] 云端任务 {cloud_task_id} 状态: {status}。继续轮询...")
        self.retry()

    elif status == "FAILED":
        logger.error(f"[PollTask] 云端任务 {cloud_task_id} 失败。")
        if hasattr(job, "fail"):
            job.fail()
        else:
            job.status = "FAILED"
        job.save()

    else:
        logger.error(f"[PollTask] 未知状态: {status}")
        if hasattr(job, "fail"):
            job.fail()
        job.save()
