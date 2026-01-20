import logging

from celery import shared_task

from apps.media_assets.services.ingest import IngestionService

logger = logging.getLogger(__name__)


@shared_task
def ingest_media_files(asset_id):
    """
    (V5.1 重构版)
    异步任务入口：委托 IngestionService 执行具体的媒资摄入逻辑。
    """
    service = IngestionService()
    return service.execute(asset_id)
