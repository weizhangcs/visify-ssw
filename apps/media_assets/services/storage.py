# 文件路径: apps/media_assets/services/storage.py

import os
import shutil
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from django.conf import settings
from pathlib import Path
from typing import Optional

# 导入 Asset 模型用于类型提示，避免循环导入
from apps.media_assets.models import Asset

class StorageService:
    """
    一个封装了存储逻辑的服务，可以处理本地存储和AWS S3存储。
    """
    def __init__(self):
        self.storage_backend = settings.STORAGE_BACKEND
        if self.storage_backend == 's3':
            self.s3_client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)

    def save_processed_video(self, local_temp_path: str, asset: Asset) -> str:
        """
        保存处理后的视频文件。

        :param local_temp_path: 本地临时视频文件的路径
        :param asset: 关联的 Asset 对象
        :return: 文件的公开访问 URL
        """
        processed_filename = f"{asset.id}.mp4"
        if self.storage_backend == 's3':
            video_s3_key = f"{settings.AWS_S3_PROCESSED_VIDEOS_PREFIX}{processed_filename}"
            self.s3_client.upload_file(local_temp_path, settings.AWS_STORAGE_BUCKET_NAME, video_s3_key)
            return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{video_s3_key}"
        else:
            processed_video_dir = Path(settings.MEDIA_ROOT) / 'processed_videos'
            processed_video_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(local_temp_path, processed_video_dir / processed_filename)
            return f"{settings.LOCAL_MEDIA_URL_BASE}{settings.MEDIA_URL}processed_videos/{processed_filename}"

    def save_source_subtitle(self, local_srt_path: Path, asset: Asset) -> Optional[str]:
        """
        保存源字幕文件。

        :param local_srt_path: 本地源字幕文件的 Path 对象
        :param asset: 关联的 Asset 对象
        :return: 文件的公开访问 URL，如果文件不存在则返回 None
        """
        if not local_srt_path.exists():
            return None

        if self.storage_backend == 's3':
            srt_s3_key = f"{settings.AWS_S3_SOURCE_SUBTITLES_PREFIX}{asset.id}/{local_srt_path.name}"
            self.s3_client.upload_file(str(local_srt_path), settings.AWS_STORAGE_BUCKET_NAME, srt_s3_key)
            return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{srt_s3_key}"
        else:
            source_subtitle_dir = Path(settings.MEDIA_ROOT) / 'source_subtitles' / str(asset.id)
            source_subtitle_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(local_srt_path), source_subtitle_dir / local_srt_path.name)
            return f"{settings.LOCAL_MEDIA_URL_BASE}{settings.MEDIA_URL}source_subtitles/{asset.id}/{local_srt_path.name}"