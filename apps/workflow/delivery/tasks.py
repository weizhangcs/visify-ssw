# 文件路径: apps/workflow/delivery/tasks.py

import logging

from celery import shared_task

from apps.media_assets.services.storage import StorageService

from ..common.baseJob import BaseJob
from ..models import DeliveryJob

logger = logging.getLogger(__name__)


@shared_task
def run_delivery_job(job_id):
    """
    执行一个具体的分发任务。
    """
    try:
        job = DeliveryJob.objects.get(id=job_id)
    except DeliveryJob.DoesNotExist:
        logger.error(f"找不到 ID 为 {job_id} 的分发任务。")
        return

    # [FIX 4a] 检查源任务，如果源任务不是 QA_PENDING，则不应运行
    source_job = job.source_object
    if not source_job:
        logger.error(f"分发任务 {job_id} 找不到源对象。任务失败。")
        job.fail()
        job.save()
        return

    if source_job.status != BaseJob.STATUS.QA_PENDING:
        logger.error(f"源任务 {source_job.id} 状态为 {source_job.status} (不是 QA_PENDING)。分发任务 {job_id} 中止。")
        # 如果源任务已经失败，我们也标记分发失败
        job.fail()
        job.save()
        return

    # 源任务状态正确 (QA_PENDING)，我们开始处理
    job.start()
    job.save()

    try:
        # 确保源文件存在
        if not hasattr(source_job, "output_file") or not source_job.output_file.path:
            raise ValueError(f"源对象 {source_job} 没有可用的 output_file。")

        local_file_path = source_job.output_file.path  # noqa: F841

        # 调用 StorageService 执行上传
        storage_service = StorageService()  # noqa: F841

        # [Refinery适配] 暂时移除旧版 TranscodingJob 的分发逻辑
        # 如果 DeliveryJob 需要支持 Refinery 产物，需在此处实现新的逻辑 (例如上传 Material 的 Proxy)
        raise NotImplementedError(
            "Delivery for legacy TranscodingJob is deprecated. Please implement Refinery delivery."
        )

        # 回写最终 URL 到 DeliveryJob
        # ...

        logger.info(f"分发任务 {job_id} 成功完成！URL: {final_url}")  # noqa: F821

    except Exception as e:
        logger.error(f"分发任务 {job_id} 失败: {e}", exc_info=True)
        job.fail()
        job.save()

        raise e
