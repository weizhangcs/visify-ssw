# 文件路径: apps/workflow/common/tasks.py

import logging

from celery import shared_task
from django.apps import apps

from apps.workflow.common.cloud_client import CloudApiService
from visify_ssw.celery import app as celery_app

logger = logging.getLogger(__name__)


@shared_task(
    bind=True, name="apps.workflow.common.tasks.poll_cloud_task_general", max_retries=100, default_retry_delay=30
)
def poll_cloud_task_general(self, model_name, job_id, cloud_task_id, on_complete_task_name, on_complete_kwargs):
    """
    (V1.2 - 边界对齐版)
    在 workflow 内部进行通用轮询，不跨 App 边界。
    """
    try:
        # 始终使用 "workflow" label，因为所有业务模型都在这个 App 下
        JobModel = apps.get_model("workflow", model_name)
        job = JobModel.objects.get(id=job_id)
    except Exception as e:
        logger.error(f"[CommonPoller] 无法定位 workflow.{model_name} (ID: {job_id}): {e}")
        return

    service = CloudApiService()
    success, data = service.get_task_status(cloud_task_id)

    if not success:
        self.retry()
        return

    status = data.get("status")
    if status == "COMPLETED":
        # 任务成功，下发回调
        celery_app.send_task(
            on_complete_task_name, kwargs={"job_id": str(job_id), "cloud_task_data": data, **on_complete_kwargs}
        )
    elif status in ["PENDING", "RUNNING"]:
        self.retry()
    else:
        # 失败处理：统一调用 BaseJob 的状态流转方法
        if hasattr(job, "fail"):
            job.fail()
        else:
            job.status = "FAILED"
        job.save()
