# 文件路径: apps/refinery/models.py

import logging
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition
from model_utils.models import TimeStampedModel

logger = logging.getLogger(__name__)


class Material(TimeStampedModel):
    """
    [精炼物料] (The Refined Material)
    定位：从物理 Media 到 语义推理之间的核心资产层。
    职责：持有所有标准化的生产介质、结构化文本和视觉索引。
    """

    class Status(models.TextChoices):
        # 初始与中间态
        PENDING = "PENDING", _("待处理")
        FAILED = "FAILED", _("处理失败")

        # 本地精炼子状态 (细化执行态)
        PROBING = "PROBING", _("元数据探测中")  # 产出: Duration, Waveform
        TRANSCODING = "TRANSCODING", _("标准化转码中")  # 产出: Proxy
        HLS_FRAGMENTING = "HLS_FRAGMENTING", _("HLS切片中")  # 产出: HLS
        ANALYZING_TEXT = "ANALYZING_TEXT", _("文本清洗中")  # 产出: Dialogue JSON
        SLICING = "SLICING", _("视觉切片中")  # 产出: Slices
        FRAME_EXTRACTING = "FRAME_EXTRACTING", _("提取关键帧中")  # 产出: Slices, Keyframes
        SYNCING = "SYNCING", _("云端同步中")
        CHARACTER_RECOGNIZING = "CHARACTER_RECOGNIZING", _("角色识别中")

        # 终态与兜底
        READY = "READY", _("就绪 (Production Ready)")
        PROCESSING = "PROCESSING", _("其他加工中")  # 预留给音频算法等扩展业务

    # --- 1. 身份与关联 ---
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 采用 OneToOne 建立物料与媒体的一一映射
    media = models.OneToOneField(
        "media_assets.Media", on_delete=models.CASCADE, related_name="material", verbose_name=_("源媒体文件")
    )

    # --- 2. 状态机控制 ---
    # 状态机仅保护“原子性”，不负责“编排逻辑”
    status = FSMField(default=Status.PENDING, choices=Status.choices, protected=True, verbose_name=_("精炼进度状态"))

    # --- 3. 本地标准化产出 (Local Artifacts) ---
    # 存储在 Edge 端，用于前端预览和本地算法输入
    proxy_video = models.CharField(max_length=1024, blank=True, verbose_name=_("代理视频 (720p)地址"))
    hls_playlist = models.CharField(max_length=1024, blank=True, verbose_name=_("HLS 播放列表索引文件地址"))
    waveform_data = models.JSONField(default=list, blank=True, verbose_name=_("波形JSON"))

    # --- 4. 结构化生产数据 (Structured Data) ---
    # 取代文件流转，直接存入 JSONB 字段
    # [对白轨] 格式: List[Dict] 包含 start, end, text, speaker
    dialogue_track = models.JSONField(default=list, blank=True, verbose_name=_("结构化对白数据"))

    # [视觉索引] 格式: List[Dict] 包含 slice_id, start, end, frames_count
    visual_slices = models.JSONField(default=list, blank=True, verbose_name=_("视觉切片索引"))

    # [关键帧映射] 格式: Dict[slice_id, cloud_path/local_path]
    keyframe_map = models.JSONField(default=dict, blank=True, verbose_name=_("关键帧映射表"))

    # --- 5. 云端锚点 (Cloud Anchors - 传输层产出) ---
    # 记录同步到 GCS/S3 后的路径，供下游 Inference 直接引用
    cloud_proxy_path = models.CharField(max_length=1024, blank=True, null=True)
    cloud_slices_path = models.CharField(max_length=1024, blank=True, null=True)
    cloud_dialogue_path = models.CharField(max_length=1024, blank=True, null=True)

    # --- 6. 技术元数据与异常记录 ---
    duration = models.FloatField(default=0.0, verbose_name=_("物理时长"))
    tech_meta = models.JSONField(default=dict, blank=True, verbose_name=_("FFprobe 元数据"))
    error_log = models.TextField(blank=True, default="", verbose_name=_("错误日志"))

    # --- 7. 生产管线的metrics ---
    pipeline_metrics = models.JSONField(default=dict, blank=True, verbose_name=_("管线执行指标"))

    # --- 8. 状态机流转定义 ---
    @transition(field=status, source=Status.PENDING, target=Status.PROBING)
    def start_probing(self):
        """开始探测元数据"""
        pass

    @transition(field=status, source=Status.PENDING, target=Status.ANALYZING_TEXT)
    def start_analyzing_text(self):
        """开始本地加工 (文本清洗)"""
        pass

    @transition(field=status, source=Status.PENDING, target=Status.TRANSCODING)
    def start_transcoding(self):
        """开始本地加工 (转码)"""
        pass

    @transition(field=status, source=Status.PENDING, target=Status.HLS_FRAGMENTING)
    def start_hls_fragmenting(self):
        """开始本地加工 (HLS)"""
        pass

    @transition(field=status, source=Status.PENDING, target=Status.SLICING)
    def start_slicing(self):
        """开始视觉切片"""
        pass

    @transition(field=status, source=Status.PENDING, target=Status.FRAME_EXTRACTING)
    def start_frame_extracting(self):
        """开始视觉切片"""
        pass

    @transition(field=status, source=Status.PENDING, target=Status.SYNCING)
    def start_syncing(self):
        """开始云端同步"""
        pass

    @transition(field=status, source=Status.PENDING, target=Status.CHARACTER_RECOGNIZING)
    def start_character_recognizing(self):
        """开始云端同步"""
        pass

    # 定义从所有“执行中”状态回到 PENDING 的合法路径
    @transition(
        field=status,
        source=[
            Status.PROBING,
            Status.TRANSCODING,
            Status.ANALYZING_TEXT,
            Status.SLICING,
            Status.SYNCING,
            Status.FRAME_EXTRACTING,
            Status.HLS_FRAGMENTING,
            Status.CHARACTER_RECOGNIZING,
        ],
        target=Status.PENDING,
    )
    def finish_current_task(self):
        """
        [合法出口] 原子任务完成，回归 PENDING 决策位。
        """
        logger.info(f"Task finished for {self.id}, returning to PENDING for re-scheduling.")

    @transition(field=status, source=Status.PENDING, target=Status.READY)
    def mark_ready(self):
        """标记为就绪"""
        pass

    @transition(field=status, source="*", target=Status.FAILED)
    def handle_failure(self, error_msg):
        """处理失败"""
        self.error_log = error_msg

    class Meta:
        verbose_name = _("精炼物料")
        verbose_name_plural = _("精炼物料")
        ordering = ["-created"]

    def __str__(self):
        return f"Material({self.media.title}) -> {self.status}"
