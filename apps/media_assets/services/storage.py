# 文件路径: apps/media_assets/services/storage.py

import logging
import shutil
from pathlib import Path

import boto3
from django.conf import settings

from apps.configuration.models import IntegrationSettings
from apps.media_assets.models import Media

logger = logging.getLogger(__name__)


# --- Helper to load dynamic settings ---
def get_integration_settings():
    """动态加载 IntegrationSettings，提供安全回退。"""
    try:
        return IntegrationSettings.get_solo()
    except Exception:
        return None


class StorageService:
    """
    (V5.3 - HLS Support)
    基于 IntegrationSettings 动态切换本地存储或 S3 存储的通用服务。
    新增 HLS 文件夹存储支持。
    """

    def __init__(self):
        settings_obj = get_integration_settings()
        self.storage_backend = getattr(settings_obj, "storage_backend", settings.FINAL_STORAGE_BACKEND)

        if self.storage_backend == "s3":
            self.s3_client = boto3.client("s3", region_name=settings.AWS_S3_REGION_NAME)
        else:
            self.s3_client = None

        logger.info(f"StorageService 初始化，后端类型: {self.storage_backend}")

    def save_processed_video(self, local_temp_path: str, media: Media) -> str:
        # ... (保持原有的 save_processed_video 方法不变) ...
        base_dir = Path(settings.MEDIA_ROOT) / "source_files" / str(media.asset.id)
        processed_video_dir = base_dir / "processed_media"
        processed_video_dir.mkdir(parents=True, exist_ok=True)
        processed_filename = f"{media.id}.mp4"
        final_path = processed_video_dir / processed_filename

        if self.storage_backend == "s3":
            s3_key = f"source_files/{media.asset.id}/processed_media/{processed_filename}"
            self.s3_client.upload_file(local_temp_path, settings.AWS_STORAGE_BUCKET_NAME, s3_key)
            if settings.AWS_S3_CUSTOM_DOMAIN:
                return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_key}"  # noqa: E231
            else:
                return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"  # noqa: E231
        else:
            shutil.move(local_temp_path, final_path)
            relative_path = final_path.relative_to(Path(settings.MEDIA_ROOT))
            return f"{settings.MEDIA_URL}{relative_path}"
