from pathlib import Path
from typing import Dict, List

from ...schemas import FrameDataInput


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

    def _handle_frame_extract(self, target, result: Dict[str, List[Dict]]):
        # result 现在是 keyframe_map 的内容
        # 确保 keyframe_map 存储的是 FrameDataInput，并进行一次校验
        processed_map = {
            slice_id: [FrameDataInput(**frame_data).model_dump() for frame_data in frames]
            for slice_id, frames in result.items()
        }
        target.keyframe_map = processed_map

    def _check_frame_extract_ready(self, target):
        return bool(target.proxy_video) and bool(target.visual_slices)

    def _check_frame_extract_done(self, target):
        # 检查 keyframe_map 是否已填充
        return bool(target.keyframe_map) and any(bool(v) for v in target.keyframe_map.values())
