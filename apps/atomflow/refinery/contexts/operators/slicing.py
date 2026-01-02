from ...schemas import VisualSliceItem


class SlicingContextMixin:
    def _payload_slicing(self, target):
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel
        return {
            "proxy_path": str(abs_proxy_path),
            "duration": target.duration,
            "dialogue_track": target.dialogue_track,
            "waveform_data": target.waveform_data,
        }

    def _handle_slicing(self, target, result):
        raw_slices = result.get("slices", [])
        target.visual_slices = [VisualSliceItem(**s).model_dump() for s in raw_slices]

    def _check_slicing_ready(self, target):
        return bool(target.proxy_video) and bool(target.dialogue_track)

    def _check_slicing_done(self, target):
        return bool(target.visual_slices)
