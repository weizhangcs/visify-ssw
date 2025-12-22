# 文件路径: apps/media_assets/services/storage.py

import logging
import os
import shutil
from pathlib import Path

import boto3
from django.conf import settings

from apps.configuration.models import IntegrationSettings
from apps.media_assets.models import Media
from apps.workflow.models import TranscodingJob

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

    def save_transcoded_video(self, local_temp_path: str, job: TranscodingJob) -> str:
        """
        [Legacy] 保存单文件转码结果 (MP4)。
        保留此方法以兼容旧的转码任务或特定格式需求。
        """
        asset_id = job.media.asset.id
        job_id = job.id
        container = job.profile.container
        final_filename = f"{job_id}.{container}"

        if self.storage_backend == "s3":
            s3_key = f"transcoding_outputs/{asset_id}/{final_filename}"
            self.s3_client.upload_file(local_temp_path, settings.AWS_STORAGE_BUCKET_NAME, s3_key)

            if settings.AWS_S3_CUSTOM_DOMAIN:
                return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_key}"  # noqa: E231
            else:
                return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{s3_key}"  # noqa: E231
        else:
            final_dir = Path(settings.MEDIA_ROOT) / "transcoding_outputs" / str(asset_id)
            final_dir.mkdir(parents=True, exist_ok=True)
            final_path = final_dir / final_filename

            if os.path.exists(local_temp_path):
                shutil.move(local_temp_path, final_path)

            relative_path_str = f"transcoding_outputs/{asset_id}/{final_filename}"
            job.output_file.name = relative_path_str
            job.save(update_fields=["output_file"])

            base = settings.LOCAL_MEDIA_URL_BASE.rstrip("/")
            media_prefix = settings.MEDIA_URL.strip("/")
            return f"{base}/{media_prefix}/{relative_path_str}"

    def save_proxy_and_hls(self, proxy_path: Path, hls_dir: Path, job: TranscodingJob) -> dict:
        """
        [V5.6 Fix] 保存 Proxy MP4 和 HLS 产物。
        返回字典: { "hls_url": "...", "proxy_file_path": "..." }
        """
        asset_id = str(job.media.asset.id)
        job_id = str(job.id)

        # 基础目录: transcoding_outputs/{asset_id}/{job_id}/
        base_rel_dir = f"transcoding_outputs/{asset_id}/{job_id}"

        # 1. 构造相对路径
        proxy_rel_path = f"{base_rel_dir}/proxy.mp4"
        hls_rel_base = f"{base_rel_dir}/hls"
        playlist_rel_path = f"{hls_rel_base}/index.m3u8"

        if self.storage_backend == "s3":
            # Upload Proxy
            self.s3_client.upload_file(str(proxy_path), settings.AWS_STORAGE_BUCKET_NAME, proxy_rel_path)

            # Upload HLS
            for root, dirs, files in os.walk(hls_dir):
                for file in files:
                    local_p = os.path.join(root, file)
                    rel_p = os.path.relpath(local_p, hls_dir).replace(os.sep, "/")
                    s3_key = f"{hls_rel_base}/{rel_p}"

                    extra_args = {}
                    if file.endswith(".m3u8"):
                        extra_args = {"ContentType": "application/vnd.apple.mpegurl", "CacheControl": "max-age=0"}
                    elif file.endswith(".ts"):
                        extra_args = {
                            "ContentType": "video/mp2t",
                            "CacheControl": "public, max-age=31536000, immutable",
                        }

                    self.s3_client.upload_file(local_p, settings.AWS_STORAGE_BUCKET_NAME, s3_key, ExtraArgs=extra_args)

            # 构造返回值
            if settings.AWS_S3_CUSTOM_DOMAIN:
                hls_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{playlist_rel_path}"  # noqa: E231
            else:
                hls_url = (
                    f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{playlist_rel_path}"  # noqa: E231
                )

            return {"hls_url": hls_url, "proxy_file_path": proxy_rel_path}

        else:
            # Local Storage
            final_base_dir = Path(settings.MEDIA_ROOT) / base_rel_dir
            if final_base_dir.exists():
                shutil.rmtree(final_base_dir)
            final_base_dir.mkdir(parents=True, exist_ok=True)

            # Move Proxy
            shutil.move(str(proxy_path), str(final_base_dir / "proxy.mp4"))

            # Move HLS
            # 注意：如果 hls 目录不存在，需要创建
            (final_base_dir / "hls").mkdir(exist_ok=True)
            # shutil.move(src, dst) 如果 dst 是目录，会把 src 移到 dst 里面成为子目录
            # 我们希望 hls_dir 的*内容*变为 final_base_dir/hls 的内容，或者把 hls_dir 整个移过去变成 final_base_dir/hls
            # 这里最简单的是把生成的 hls 文件夹直接移动到 final_base_dir 下，重命名为 'hls'
            # 如果 hls_dir 的名字本来就是 'hls'，那直接移进去可能会变成 .../hls/hls，要小心

            # 修正移动逻辑：
            # hls_dir 是 /.../temp/.../hls
            # 目标是 /.../transcoding_outputs/.../hls

            # 先删除可能存在的目标 hls 目录
            target_hls_dir = final_base_dir / "hls"
            if target_hls_dir.exists():
                shutil.rmtree(target_hls_dir)

            shutil.move(str(hls_dir), str(target_hls_dir))

            # 构造 Nginx URL
            base = settings.LOCAL_MEDIA_URL_BASE.rstrip("/")
            media_prefix = settings.MEDIA_URL.strip("/")

            hls_url = f"{base}/{media_prefix}/{playlist_rel_path}"

            # [关键修复] 返回字典
            return {"hls_url": hls_url, "proxy_file_path": proxy_rel_path}
