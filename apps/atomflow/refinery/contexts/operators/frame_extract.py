from pathlib import Path
from typing import Dict, List

from apps.common.schemas.dataset.schemas import KeyframeItem


class FrameExtractContextMixin:
    """
    Context Mixin for frame extraction.

    Provides methods to generate payloads for and handle results from the FrameExtractorService.
    """

    @property
    def media_root(self) -> Path:
        raise NotImplementedError

    def _payload_frame_extract(self, target):
        """
        Generate payload for the FrameExtractorService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the proxy video path, slice list,
            absolute output directory, and relative directory for storage.
        """
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel
        rel_dir = Path(f"refinery/{target.id}/frames")
        abs_output_dir = self.media_root / rel_dir

        return {
            "proxy_path": str(abs_proxy_path),
            "slices": target.slices,
            "output_dir": str(abs_output_dir),
            "rel_dir": str(rel_dir),
        }

    def _handle_frame_extract(self, target, result: Dict[str, List[Dict]]):
        """
        Handle the result from the FrameExtractorService.

        Updates the Material's keyframe_map with the extracted frame data.

        Args:
            target: The Material instance.
            result: The keyframe_map dictionary (slice_id -> frame_list).
        """
        # [Phase 1 Refactor] 移除强制排序和 Index 生成
        # 理由：VSS Cloud 仅依赖 frame_id (UUID)，且文件名已包含物理顺序。
        # 强行维护全局 index 成本高且无意义。
        all_raw_frames = []
        for frames in result.values():
            all_raw_frames.extend(frames)

        processed_map = {}
        final_flat_list = []

        for frame_data in all_raw_frames:
            # 校验并序列化
            item = KeyframeItem(**frame_data).model_dump()
            final_flat_list.append(item)

            # 按 slice_id 分组回填 map
            s_id = item["slice_id"]
            if s_id not in processed_map:
                processed_map[s_id] = []
            processed_map[s_id].append(item)

        target.keyframe_map = processed_map
        target.frames = final_flat_list

    def _check_frame_extract_ready(self, target):
        """
        Check if the Frame Extract task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if proxy video and slices exist, False otherwise.
        """
        return bool(target.proxy_video) and bool(target.slices)

    def _check_frame_extract_done(self, target):
        """
        Check if the Frame Extract task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if keyframe_map is populated, False otherwise.
        """
        return bool(target.keyframe_map) and any(bool(v) for v in target.keyframe_map.values())
