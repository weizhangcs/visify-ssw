# 文件路径: apps/media_assets/models.py

import logging
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

logger = logging.getLogger(__name__)


class AssetType(models.TextChoices):
    """
    [Core Contract]
    与 Cloud 端 Schema 对齐。
    Cloud 端将同步增加 'other' 枚举值以支持兜底。
    """

    FEATURE_FILM = "feature_film", "电影 (Feature Film)"
    SERIES_EPISODE = "series_episode", "剧集 (Series Episode)"
    SHORT_CLIP = "short_clip", "短片 (Short Clip)"
    DOCUMENTARY = "documentary", "纪录片 (Documentary)"
    RAW_FOOTAGE = "raw_footage", "素材 (Raw Footage)"
    # [恢复] 兜底选项，Cloud端需同步支持
    OTHER = "other", "其他 (Other)"


class ContentGenre(models.TextChoices):
    DRAMA = "drama", "Drama"
    COMEDY = "comedy", "Comedy"
    ACTION = "action", "Action"
    THRILLER = "thriller", "Thriller"
    SCI_FI = "sci_fi", "Sci-Fi"
    ROMANCE = "romance", "Romance"
    HORROR = "horror", "Horror"
    DOCUMENTARY = "documentary", "Documentary"
    ANIMATION = "animation", "Animation"
    FANTASY = "fantasy", "Fantasy"
    OTHER = "other", "Other"


class VideoOrientation(models.TextChoices):
    LANDSCAPE = "landscape", "横屏 (Landscape)"
    PORTRAIT = "portrait", "竖屏 (Portrait)"
    UNKNOWN = "unknown", "未知 (Unknown)"


# --- 定义动态路径函数 ---
def get_media_upload_path(instance, filename):
    return f"source_files/{instance.asset.id}/media/{filename}"


def get_subtitle_upload_path(instance, filename):
    return f"source_files/{instance.asset.id}/subtitles/{filename}"


# =============================================================================
# [Deprecated] 仅保留以兼容旧迁移文件引用 (如 0003_media_waveform_data.py)。
# =============================================================================
def get_waveform_upload_path(instance, filename):
    return f"source_files/{instance.asset.id}/waveforms/{filename}"


# --- Asset 模型 (保持不变) ---
class Asset(TimeStampedModel):
    # [恢复] 默认值设为 OTHER，作为安全兜底
    asset_type = models.CharField(_("Asset Type"), max_length=50, choices=AssetType.choices, default=AssetType.OTHER)

    content_genre = models.CharField(
        _("Genre"), max_length=50, choices=ContentGenre.choices, default=ContentGenre.OTHER
    )

    orientation = models.CharField(
        max_length=20,
        choices=VideoOrientation.choices,
        default=VideoOrientation.UNKNOWN,
        verbose_name="画幅方向",
    )

    # [新增] 角色列表：存储 JSON 格式 List[str]，例如 ["Iron Man", "Captain America"]
    # 使用 JSONField 方便后续扩展 (如包含角色别名)
    known_characters = models.JSONField(
        _("Known Characters"), default=list, blank=True, help_text="List of character names known in this asset."
    )

    COPYRIGHT_STATUS_CHOICES = (("pending", "待定"), ("cleared", "已授权"), ("owned", "自有版权"), ("restricted", "受限"))
    LANGUAGE_CHOICES = (("zh-CN", "中文 (简体)"), ("en-US", "英语 (美国)"))
    UPLOAD_STATUS_CHOICES = (("pending", "等待文件上传"), ("uploading", "上传中"), ("completed", "上传完成"), ("failed", "上传失败"))

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, verbose_name="资产标题 (Title)")
    description = models.TextField(blank=True, null=True, verbose_name="描述")
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default="zh-CN", verbose_name="语言")
    copyright_status = models.CharField(
        max_length=20, choices=COPYRIGHT_STATUS_CHOICES, default="pending", verbose_name="版权状态"
    )
    upload_status = models.CharField(
        max_length=20, choices=UPLOAD_STATUS_CHOICES, default="pending", verbose_name="文件上传状态"
    )

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "内容资产 (Asset)"
        verbose_name_plural = "内容资产 (Asset)"
        ordering = ["-created"]


# --- Media 模型 (V5.0 重构版) ---
class Media(TimeStampedModel):
    """
    (V5.0 终极纯净版)
    媒体文件实体，仅作为“唯一真理源” (Source of Truth)。
    移除了所有冗余 URL 字段，增加了业务逻辑方法。
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="medias", verbose_name="所属资产 (Asset)")
    title = models.CharField(max_length=255, verbose_name="媒体标题")
    sequence_number = models.PositiveIntegerField(default=1, verbose_name="序号")

    # --- 核心元数据 ---
    # [新增] 时长字段：默认 0.0，由 Transcoding Task 精确回填
    duration = models.FloatField(default=0.0, verbose_name="时长 (秒)", help_text="视频精确时长，由转码任务自动更新")

    # 源文件 (Master) - 配合 EdgeLocalStorage 自动生成指向 9999 的绝对 URL
    source_video = models.FileField(upload_to=get_media_upload_path, blank=True, null=True, verbose_name="源视频文件")
    source_subtitle = models.FileField(
        upload_to=get_subtitle_upload_path, blank=True, null=True, verbose_name="源字幕文件 (SRT)"
    )

    def __str__(self):
        return f"{self.asset.title} - {self.sequence_number:02d} - {self.title}"  # noqa: E231

    def get_best_playback_url(self, encoding_profile=None):
        """
        [业务逻辑] 智能获取最佳播放地址 (绝对路径)。
        策略:
        1. [Refinery] 优先查找 Material 的 HLS Playlist。
        2. [Fallback] 回退到 source_video。
        3. 强制确保返回绝对 URL。
        """

        target_url = None

        # 1. 尝试查找 Refinery Material (HLS)
        # Material 通过 OneToOne 关联到 Media，related_name="material"
        if hasattr(self, "material") and self.material.hls_playlist:
            # material.hls_playlist 通常存储相对路径，ensure_absolute_url 会处理
            target_url = self.material.hls_playlist

        # 2. 兜底策略：使用源文件
        if not target_url and self.source_video:
            # EdgeLocalStorage 已经保证了这里是 http://... 的绝对路径
            # 但为了双重保险 (防止有人改回 FileSystemStorage)，下方会统一处理
            target_url = self.source_video.url

        # 3. 统一格式化为绝对路径 (Private Helper Logic)
        return self.ensure_absolute_url(target_url)

    def ensure_absolute_url(self, url_path):
        """
        确保 URL 是绝对路径 (http/https 开头)。
        如果是相对路径，则拼接 settings.LOCAL_MEDIA_URL_BASE。
        同时确保路径包含 MEDIA_URL 前缀 (适配 Nginx location /media/)。
        """
        if not url_path:
            return ""

        url_str = str(url_path)
        if url_str.startswith(("http://", "https://")):
            return url_str

        # 拼接逻辑
        base = settings.LOCAL_MEDIA_URL_BASE.rstrip("/")
        path = url_str.lstrip("/")

        # [Fix] 检查并补全 MEDIA_URL 前缀
        # Nginx 配置了 location /media/，所以所有资源路径必须以 media/ 开头
        # 数据库中存储的 hls_playlist 等字段通常是 "refinery/..." 相对路径，缺少 media 前缀
        media_prefix = settings.MEDIA_URL.strip("/")  # e.g., "media"

        if media_prefix and not path.startswith(f"{media_prefix}/"):
            path = f"{media_prefix}/{path}"

        return f"{base}/{path}"

    def get_best_processing_path(self):
        """
        [新增] 获取最佳处理源文件的物理路径 (用于 AI/CV 处理)。
        策略:
        1. [TODO] 未来可对接 Material 的 Proxy Video (需处理路径映射)。
        2. [Fallback] 目前兜底使用 source_video (原始母带)。

        注意：返回的是文件系统的绝对路径 (path)，而非 URL。
        """
        target_path = None

        if not target_path and self.source_video:
            try:
                target_path = self.source_video.path
                logger.warning(f"Proxy not found, falling back to Source Video: {target_path}")
            except NotImplementedError:
                # 处理某些云存储 backend 不支持 .path 的情况
                logger.error("Storage backend does not support .path access.")

        return target_path

    class Meta:
        verbose_name = "媒体文件 (Media)"
        verbose_name_plural = "媒体文件 (Media)"
        ordering = ["asset", "sequence_number"]
