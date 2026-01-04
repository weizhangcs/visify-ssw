import logging
import time
from pathlib import Path

from django.conf import settings

from apps.common.atomflow.base_contexts import BaseAtomicContext

from ..models import Material, RefineryAtomPipeline
from .operators.audio_analyze import AudioAnalyzeContextMixin
from .operators.character_refine import CharacterRefineContextMixin
from .operators.frame_extract import FrameExtractContextMixin
from .operators.frame_probe import FrameProbeContextMixin
from .operators.hls import HLSContextMixin
from .operators.probe import ProbeContextMixin
from .operators.slicing import SlicingContextMixin
from .operators.sync import SyncContextMixin
from .operators.text_analyze import TextAnalyzeContextMixin

# 引入所有算子 Mixin
from .operators.transcode import TranscodeContextMixin
from .operators.visual_analyzer import VisualAnalyzerContextMixin

logger = logging.getLogger(__name__)


class RefineryAtomicContext(
    BaseAtomicContext,
    TranscodeContextMixin,
    ProbeContextMixin,
    HLSContextMixin,
    SlicingContextMixin,
    AudioAnalyzeContextMixin,
    FrameProbeContextMixin,  # 新增
    FrameExtractContextMixin,
    TextAnalyzeContextMixin,
    CharacterRefineContextMixin,
    SyncContextMixin,
    VisualAnalyzerContextMixin,
):
    """
    旁路业务上下文：负责 Material 与 算子之间的数据平配。
    通过 Mixin 模式聚合各算子逻辑。
    """

    @property
    def media_root(self) -> Path:
        return Path(settings.MEDIA_ROOT)

    def get_target_instance(self) -> Material:
        return Material.objects.select_related("media", "media__asset", "pipeline", "pipeline__rule").get(
            id=self.target_id
        )

    @property
    def pipeline(self):
        try:
            pipeline = self.target.pipeline
            if pipeline and not hasattr(pipeline, "mode"):
                pipeline.mode = pipeline.rule.mode
            return pipeline
        except RefineryAtomPipeline.DoesNotExist:
            return None

    def get_payload(self, op_slug: str):
        target = self.target
        handler = getattr(self, f"_payload_{op_slug}", None)
        if handler:
            return handler(target)
        return {}

    def handle_result(self, op_slug: str, result: dict):
        target = self.target
        handler = getattr(self, f"_handle_{op_slug}", None)
        if handler:
            handler(target, result)
        else:
            logger.warning(f"[Atomflow] 未找到 {op_slug} 的结果处理逻辑")
            return

        target.save()
        logger.info(f"[Atomflow] {op_slug} 结果已回填至 Material {target.id}")
        self._update_pipeline_metrics(op_slug)

    def check_is_ready(self, slug: str) -> bool:
        target = self.target
        handler = getattr(self, f"_check_{slug}_ready", None)
        if handler:
            return handler(target)
        return True

    def check_is_done(self, slug: str) -> bool:
        target = self.target
        handler = getattr(self, f"_check_{slug}_done", None)
        if handler:
            return handler(target)
        return False

    def _update_pipeline_metrics(self, op_slug: str):
        pipeline = self.pipeline
        if not pipeline:
            return

        rule_config = pipeline.rule.rules_config
        step_info = next((s for s in rule_config if s["unit_slug"] == op_slug), None)

        if step_info:
            seq = str(step_info["seq"])
            metrics = pipeline.metrics or {}
            if seq not in metrics or metrics[seq].get("status") != "SUCCESS":
                metrics[seq] = {"slug": op_slug, "status": "SUCCESS", "finished_at": time.time()}
                pipeline.metrics = metrics
                pipeline.save(update_fields=["metrics"])
                logger.info(f"[Atomflow] Pipeline {pipeline.id} metrics updated for step {seq} ({op_slug})")
