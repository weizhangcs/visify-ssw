import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from apps.common.atomflow.base_models import BaseAtomflowRule, BaseAtomPipeline, BaseAtomUnit


class RefineryAtomUnit(BaseAtomUnit):
    """
    [能力层] 精炼算子定义
    具体算子实现逻辑在 apps.atomflow.refinery.context.RefineryAtomicContext 中
    """

    # 显式指定 UUID 作为主键
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        verbose_name = "Atomflow精炼算子"
        verbose_name_plural = "Atomflow精炼算子"

    def __str__(self):
        return f"{self.name} ({self.slug})"


class RefineryAtomRule(BaseAtomflowRule):
    """
    [逻辑层] 精炼编排规则
    定义了从 Raw Media 到 Refined Material 的具体工序 (如: Transcode -> Probe -> Slicing)
    """

    # 显式指定 UUID 作为主键
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        verbose_name = "Atomflow精炼规则"
        verbose_name_plural = "Atomflow精炼规则"

    def __str__(self):
        return f"{self.name} ({self.slug})"


class RefineryAtomPipeline(BaseAtomPipeline):
    """
    [实例层] 精炼执行轨迹
    记录某一个 Material 在某一个 Rule 下的执行状态与历史
    """

    # 显式指定 UUID 作为主键
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 关联具体的业务对象 (Material)
    # 这里我们保留 target_id 作为通用接口
    target_id = models.CharField(max_length=64, db_index=True, verbose_name="关联物料ID")

    # [修正] 使用 OneToOneField 强制 1:1 关系
    material = models.OneToOneField(
        "Material",
        on_delete=models.CASCADE,
        related_name="pipeline",  # 单数形式
        verbose_name="关联物料",
        null=True,
        blank=True,
    )

    rule = models.ForeignKey(RefineryAtomRule, on_delete=models.PROTECT, verbose_name="使用规则")

    class Meta:
        verbose_name = "Atomflow精炼轨迹"
        verbose_name_plural = "Atomflow精炼轨迹"

    def __str__(self):
        return f"Pipeline-{self.name} (Target: {self.target_id})"


class Material(TimeStampedModel):
    """
    [精炼物料] (The Refined Material)
    定位：Atomflow Refinery 的核心产出容器。
    职责：持有所有标准化的生产介质、结构化文本和视觉索引。
    注意：它不再维护状态 (Status)，状态由 Pipeline 接管。
    """

    # --- 1. 身份与关联 ---
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 采用 OneToOne 建立物料与媒体的一一映射
    media = models.OneToOneField(
        "media_assets.Media", on_delete=models.CASCADE, related_name="material", verbose_name=_("源媒体文件")
    )

    # --- 2. 本地标准化产出 (Local Artifacts) ---
    proxy_video = models.CharField(max_length=1024, blank=True, verbose_name=_("代理视频 (720p)地址"))
    hls_playlist = models.CharField(max_length=1024, blank=True, verbose_name=_("HLS 播放列表索引文件地址"))
    waveform_data = models.JSONField(default=list, blank=True, verbose_name=_("波形JSON"))

    # --- 3. 结构化生产数据 (Structured Data) ---
    dialogue_track = models.JSONField(default=list, blank=True, verbose_name=_("结构化对白数据"))
    visual_slices = models.JSONField(default=list, blank=True, verbose_name=_("视觉切片索引"))
    keyframe_map = models.JSONField(default=dict, blank=True, verbose_name=_("关键帧映射表"))

    # --- 4. 云端锚点 (Cloud Anchors) ---
    cloud_proxy_path = models.CharField(max_length=1024, blank=True, null=True)
    cloud_slices_path = models.CharField(max_length=1024, blank=True, null=True)
    cloud_dialogue_path = models.CharField(max_length=1024, blank=True, null=True)

    # --- 5. 技术元数据与异常记录 ---
    duration = models.FloatField(default=0.0, verbose_name=_("物理时长"))
    tech_meta = models.JSONField(default=dict, blank=True, verbose_name=_("FFprobe 元数据"))
    error_log = models.TextField(blank=True, default="", verbose_name=_("错误日志"))

    class Meta:
        verbose_name = _("精炼物料")
        verbose_name_plural = _("精炼物料")
        ordering = ["-created"]

    def __str__(self):
        return f"Material({self.media.title})"
