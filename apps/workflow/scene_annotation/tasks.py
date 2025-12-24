import logging

from celery import shared_task

from .services.service import SceneAnnotationService

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="media_queue", max_retries=3)
def run_scene_annotation_pipeline(self, job_id: str, **kwargs):
    """
    [Task Shell] 场景标注异步入口
    符合文档3：无业务逻辑，仅负责调度 Service。
    """
    try:
        # 全部委托给 Service
        SceneAnnotationService.execute_pipeline(job_id=job_id)
        return f"Pipeline started for Job {job_id}"

    except Exception as e:
        logger.error(f"[Task] Execution failed for Job {job_id}: {e}")
        # 这里可以选择 self.retry()，目前暂且抛出
        raise e


@shared_task(name="apps.workflow.scene_annotation.tasks.finalize_scene_annotation")
def finalize_scene_annotation(job_id: str, cloud_task_data: dict, **kwargs):
    """
    [Task Shell] 回调入口
    遵循文档3：仅负责调度 Service.finalize_pipeline
    """
    try:
        logger.info(f"[Task] Finalizing Scene Annotation Job {job_id}")
        # 核心逻辑全部委托给 Service
        SceneAnnotationService.finalize_pipeline(job_id=job_id, cloud_task_data=cloud_task_data)

    except Exception as e:
        # Task 层只负责最后的异常兜底记录，不处理业务状态
        logger.error(f"[Task] Finalize dispatch failed for Job {job_id}: {e}", exc_info=True)
