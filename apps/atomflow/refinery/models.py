import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from apps.common.atomflow.base_models import BaseAtomflowRule, BaseAtomPipeline, BaseAtomUnit


class RefineryAtomUnit(BaseAtomUnit):
    """
    [能力层] 精炼算子定义模型。

    用于在数据库中注册和管理具体的原子算子（如 transcode, probe 等）。
    具体的算子执行逻辑封装在 apps.atomflow.refinery.context.RefineryAtomicContext 中，
    或者通过 apps.atomflow.refinery.services 下的独立 Service 实现。
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
    [逻辑层] 精炼编排规则模型。

    定义了从 Raw Media 到 Refined Material 的具体工序流程。
    例如：Transcode -> Probe -> Slicing -> Frame Extraction -> Visual Analysis。
    规则配置存储在 rules_config JSON 字段中。
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
    [实例层] 精炼执行轨迹模型。

    记录某一个 Material 在某一个 Rule 下的执行状态与历史（Metrics）。
    它是连接 Material（数据）和 Rule（逻辑）的桥梁，负责维护流程状态（PENDING, RUNNING, SUCCESS, FAILED）。
    """

    # 显式指定 UUID 作为主键
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 关联具体的业务对象 (Material)
    # 这里我们保留 target_id 作为通用接口，方便基类或其他组件引用
    target_id = models.CharField(max_length=64, db_index=True, verbose_name="关联物料ID")

    # [修正] 使用 OneToOneField 强制 1:1 关系
    # 确保一个 Material 在同一时间只能关联一个活跃的 Pipeline
    material = models.OneToOneField(
        "Material",
        on_delete=models.CASCADE,
        related_name="pipeline",  # 单数形式，强调 1:1
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
    注意：它不再维护状态 (Status)，状态由关联的 RefineryAtomPipeline 接管。
    """

    # ==========================================================================
    # 1. 身份与关联 (Identity & Relations)
    # ==========================================================================
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 采用 OneToOne 建立物料与媒体的一一映射
    media = models.OneToOneField(
        "media_assets.Media", on_delete=models.CASCADE, related_name="material", verbose_name=_("源媒体文件")
    )

    # ==========================================================================
    # 2. 本地标准化产出 (Local Artifacts)
    # ==========================================================================
    proxy_video = models.CharField(max_length=1024, blank=True, verbose_name=_("代理视频 (720p)地址"))
    hls_playlist = models.CharField(max_length=1024, blank=True, verbose_name=_("HLS 播放列表索引文件地址"))
    waveform_data = models.JSONField(default=list, blank=True, verbose_name=_("波形JSON"))

    # ==========================================================================
    # 3. 结构化生产数据 (Structured Data)
    # ==========================================================================
    # [Renamed] dialogue -> dialogues (保持复数一致性)
    slices = models.JSONField(default=list, blank=True, verbose_name=_("多模态切片容器"))
    scenes = models.JSONField(default=list, blank=True, verbose_name=_("场景容器"))
    dialogues = models.JSONField(default=list, blank=True, verbose_name=_("对白容器"))
    identified_characters = models.JSONField(default=list, blank=True, verbose_name=_("识别角色清单"))
    keyframe_map = models.JSONField(default=dict, blank=True, verbose_name=_("关键帧映射表"))

    # ==========================================================================
    # 4. 搜索与索引 (Search & Indexing)
    # ==========================================================================
    slice_vector_index_path = models.CharField(max_length=1024, blank=True, null=True, verbose_name=_("切片向量索引路径"))
    scene_vector_index_path = models.CharField(max_length=1024, blank=True, null=True, verbose_name=_("场景向量索引路径"))

    # ==========================================================================
    # 5. 技术元数据 (Technical Metadata)
    # ==========================================================================
    duration = models.FloatField(default=0.0, verbose_name=_("物理时长"))
    tech_meta = models.JSONField(default=dict, blank=True, verbose_name=_("FFprobe 元数据"))

    class Meta:
        verbose_name = _("精炼物料")
        verbose_name_plural = _("精炼物料")
        ordering = ["-created"]

    def __str__(self):
        return f"Material({self.media.title})"
