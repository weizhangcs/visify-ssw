from pathlib import Path
from typing import Dict, List

from ...schemas import FrameDataInput


class FrameExtractContextMixin:
    """
    Context Mixin for frame extraction.

    Provides methods to generate payloads for and handle results from the FrameExtractorService.
    """

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
        # Ensure keyframe_map stores valid FrameDataInput objects
        processed_map = {
            slice_id: [FrameDataInput(**frame_data).model_dump() for frame_data in frames]
            for slice_id, frames in result.items()
        }
        target.keyframe_map = processed_map

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
