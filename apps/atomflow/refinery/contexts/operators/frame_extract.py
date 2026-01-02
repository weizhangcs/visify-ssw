from pathlib import Path

from ...schemas import VisualSliceItem


class FrameExtractContextMixin:
    def _payload_frame_extract(self, target):
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel
        rel_dir = Path(f"refinery/{target.id}/frames")
        abs_output_dir = self.media_root / rel_dir

        return {
            "proxy_path": str(abs_proxy_path),
            "slices": target.visual_slices,
            "output_dir": str(abs_output_dir),
            "rel_dir": str(rel_dir),
        }

    def _handle_frame_extract(self, target, result):
        raw_slices = result.get("slices", [])
        target.visual_slices = [VisualSliceItem(**s).model_dump() for s in raw_slices]

    def _check_frame_extract_ready(self, target):
        return bool(target.proxy_video) and bool(target.visual_slices)

    def _check_frame_extract_done(self, target):
        if not target.visual_slices:
            return False
        return all(s.get("frames") for s in target.visual_slices)
