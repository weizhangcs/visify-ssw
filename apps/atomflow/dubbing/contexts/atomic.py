import logging
import time
from pathlib import Path

from django.conf import settings

from apps.atomflow.dubbing.contexts.operators.enhancement import AudioEnhancementContextMixin
from apps.atomflow.dubbing.contexts.operators.fusion import AudioVisualFusionContextMixin
from apps.atomflow.dubbing.contexts.operators.gating import AudioGatingContextMixin
from apps.atomflow.dubbing.contexts.operators.inpainting import VideoInpaintingContextMixin
from apps.atomflow.dubbing.contexts.operators.material import AudioMaterialContextMixin
from apps.atomflow.dubbing.contexts.operators.ocr import VideoOCRContextMixin
from apps.atomflow.dubbing.contexts.operators.perception import AudioPerceptionContextMixin
from apps.atomflow.dubbing.contexts.operators.script_refinement import ScriptRefinementContextMixin

# Import Mixins
from apps.atomflow.dubbing.contexts.operators.separation import AudioSeparationContextMixin
from apps.atomflow.dubbing.contexts.operators.visual import VisualAnalysisContextMixin
from apps.atomflow.dubbing.models import DubbingAtomPipeline, DubbingSession
from apps.common.atomflow.base_contexts import BaseAtomicContext

logger = logging.getLogger(__name__)


class DubbingAtomicContext(
    BaseAtomicContext,
    AudioSeparationContextMixin,
    AudioGatingContextMixin,
    AudioEnhancementContextMixin,
    AudioMaterialContextMixin,
    AudioPerceptionContextMixin,
    VideoOCRContextMixin,
    VideoInpaintingContextMixin,
    VisualAnalysisContextMixin,
    AudioVisualFusionContextMixin,
    ScriptRefinementContextMixin,
):
    """
    Dubbing 业务上下文
    """

    @property
    def media_root(self) -> Path:
        return Path(settings.MEDIA_ROOT)

    def get_target_instance(self) -> DubbingSession:
        # [Optimization] 预加载 material.media 以避免访问 file 时触发额外查询
        return DubbingSession.objects.select_related("material__media").get(id=self.target_id)

    @property
    def pipeline(self):
        try:
            return self.target.pipeline
        except DubbingAtomPipeline.DoesNotExist:
            return None

    def get_payload(self, op_slug: str):
        target = self.target
        # 确保 Session 目录存在
        session_dir = self.media_root / "dubbing" / str(target.id)
        session_dir.mkdir(parents=True, exist_ok=True)

        # 动态分发到 Mixin
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
            logger.warning(f"No handler found for {op_slug}")
            return

        target.save()
        self._update_pipeline_metrics(op_slug)

    def _relativize(self, abs_path: str) -> str:
        try:
            return str(Path(abs_path).relative_to(self.media_root))
        except ValueError:
            return abs_path

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

    def check_is_ready(self, slug: str) -> bool:
        handler = getattr(self, f"_check_{slug}_ready", None)
        if handler:
            return handler(self.target)
        return True

    def check_is_done(self, slug: str) -> bool:
        handler = getattr(self, f"_check_{slug}_done", None)
        if handler:
            return handler(self.target)
        return False
