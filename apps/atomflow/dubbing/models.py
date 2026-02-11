import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from apps.common.atomflow.base_models import BaseAtomflowRule, BaseAtomPipeline, BaseAtomUnit


class DubbingAtomUnit(BaseAtomUnit):
    """[能力层] 配音算子定义"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        verbose_name = "Dubbing配音算子"
        verbose_name_plural = "Dubbing配音算子"


class DubbingAtomRule(BaseAtomflowRule):
    """[逻辑层] 配音编排规则"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        verbose_name = "Dubbing配音规则"
        verbose_name_plural = "Dubbing配音规则"


class DubbingAtomPipeline(BaseAtomPipeline):
    """[实例层] 配音执行轨迹"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_id = models.CharField(max_length=64, db_index=True, verbose_name="关联SessionID", blank=True)

    session = models.OneToOneField(
        "DubbingSession",
        on_delete=models.CASCADE,
        related_name="pipeline",
        verbose_name="关联配音会话",
        null=True,
        blank=True,
    )
    rule = models.ForeignKey(DubbingAtomRule, on_delete=models.PROTECT, verbose_name="使用规则")

    class Meta:
        verbose_name = "Dubbing配音轨迹"
        verbose_name_plural = "Dubbing配音轨迹"


class DubbingSession(TimeStampedModel):
    """
    [配音会话] (The Dubbing Session)
    替代原脚本中的 `paths` 字典，持久化存储所有中间产物路径。
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 关联上游 Refinery 的产物
    material = models.ForeignKey(
        "atomflow.Material", on_delete=models.CASCADE, related_name="dubbing_sessions", verbose_name=_("源精炼物料")
    )

    # --- Step 1: Separation ---
    stem_vocals = models.CharField(max_length=1024, blank=True, verbose_name=_("人声分轨路径"))
    stem_inst = models.CharField(max_length=1024, blank=True, verbose_name=_("伴奏分轨路径"))

    # --- Step 2: Gating ---
    # 存储 Gating 产生的掩码统计或日志路径，实际 Mask 文件可能较大，建议存路径或 Blob
    gating_meta = models.JSONField(default=dict, blank=True, verbose_name=_("门控元数据"))
    mask_gating_path = models.CharField(max_length=1024, blank=True, verbose_name=_("门控掩码路径"))

    # --- Step 3: Enhancement ---
    track_enhanced = models.CharField(max_length=1024, blank=True, verbose_name=_("增强人声路径"))

    # --- Step 4: Material Track ---
    track_material = models.CharField(max_length=1024, blank=True, verbose_name=_("背景素材轨路径"))

    # --- Step 5: Perception Track ---
    track_perception = models.CharField(max_length=1024, blank=True, verbose_name=_("感知单声道路径"))

    # --- Step 6: Perception Analysis ---
    perception_meta = models.JSONField(default=dict, blank=True, verbose_name=_("感知分析结果"))

    # --- Step 7: Visual Analysis ---
    face_csv_path = models.CharField(max_length=1024, blank=True, verbose_name=_("人脸索引路径"))

    # --- Step 10: Fusion ---
    fused_metadata = models.JSONField(default=list, blank=True, verbose_name=_("视听融合结果"))

    # --- Step 8: OCR ---
    ocr_csv_path = models.CharField(max_length=1024, blank=True, verbose_name=_("OCR索引路径"))

    # --- Step 9: Inpainting ---
    video_clean = models.CharField(max_length=1024, blank=True, verbose_name=_("去字幕视频路径"))

    # --- Step 11: Script Refinement (Cloud) ---
    refined_script = models.JSONField(default=dict, blank=True, verbose_name=_("AI精修脚本"))

    # Debug Paths (Optional)
    debug_paths = models.JSONField(default=dict, blank=True, verbose_name=_("调试文件路径表"))

    class Meta:
        verbose_name = _("配音会话")
        verbose_name_plural = _("配音会话")
        ordering = ["-created"]

    def __str__(self):
        return f"DubbingSession({self.material.media.title if self.material else 'Unknown'})"
