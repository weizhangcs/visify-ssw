import logging

logger = logging.getLogger(__name__)


class SliceAnalyzerContextMixin:
    """
    Context Mixin for slice-level semantic analysis.
    """

    def _payload_slice_analyzer(self, target):
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
            "lang": lang,
        }

    def _handle_slice_analyzer(self, target, result):
        """
        Handle result: Update Material.slices with hydrated and analyzed data.
        """
        updated_slices = result.get("slices", [])
        if updated_slices:
            target.slices = updated_slices

    def _check_slice_analyzer_ready(self, target):
        """
        Ready if we have slices and keyframe_map (visuals ready).
        """
        return bool(target.slices and target.keyframe_map)

    def _check_slice_analyzer_done(self, target):
        """
        Done if slices have slice_analysis.
        """
        if not target.slices:
            return False
        # Check first slice for analysis data
        return any(s.get("slice_analysis") for s in target.slices)
