import logging

logger = logging.getLogger(__name__)


class AnalyzeSliceContextMixin:
    """
    Context Mixin for slice-level semantic analysis.
    """

    def _payload_analyze_slice(self, target):
        """
        Generate payload for SliceAnalyzerService.
        """
        asset = getattr(target.media, "asset", None)
        lang = "zh"
        if asset and asset.language:
            lang = asset.language.split("-")[0]

        return {
            "slices": target.slices,
            "keyframe_map": target.keyframe_map,
            # [Phase 1] 注入 SSOT 对白数据，供 Service 进行 ID 反查 (Hydration)
            "dialogues": target.dialogues,
            "lang": lang,
        }

    def _handle_analyze_slice(self, target, result):
        """
        Handle result: Update Material.slices with hydrated and analyzed data.
        """
        updated_slices = result.get("slices", [])
        if updated_slices:
            target.slices = updated_slices

    def _check_analyze_slice_ready(self, target):
        """
        Ready if we have slices and keyframe_map (visuals ready).
        """
        return bool(target.slices and target.keyframe_map)

    def _check_analyze_slice_done(self, target):
        """
        Done if slices have slice_analysis.
        """
        if not target.slices:
            return False
        # Check first slice for analysis data
        return any(s.get("slice_analysis") for s in target.slices)
