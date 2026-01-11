from apps.atomflow.refinery.schemas import FrameDataInput


class FrameProbeContextMixin:
    """
    Context Mixin for frame probing (quality assessment).

    Provides methods to generate payloads for and handle results from the FrameProbeService.
    """

    def _payload_frame_probe(self, target):
        """
        Generate payload for the FrameProbeService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the keyframe_map and the media root path.
        """
        # Frame probe requires the keyframe_map to access frame paths
        return {"keyframe_map": target.keyframe_map, "media_root": str(self.media_root)}

    def _handle_frame_probe(self, target, result: dict):
        """
        Handle the result from the FrameProbeService.

        Updates the Material's keyframe_map with quality scores and filter reasons.

        Args:
            target: The Material instance.
            result: The updated keyframe_map dictionary.
        """
        # Ensure keyframe_map stores valid FrameDataInput objects
        # Full replacement naturally supports writing back redundant data
        processed_map = {
            slice_id: [FrameDataInput(**frame_data).model_dump() for frame_data in frames]
            for slice_id, frames in result.items()
        }
        target.keyframe_map = processed_map

    def _check_frame_probe_ready(self, target):
        """
        Check if the Frame Probe task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if keyframe_map is populated, False otherwise.
        """
        # Frame probe depends on frame extraction completion
        return bool(target.keyframe_map) and any(bool(v) for v in target.keyframe_map.values())

    def _check_frame_probe_done(self, target):
        """
        Check if the Frame Probe task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if at least one frame has a quality score, False otherwise.
        """
        if not target.keyframe_map:
            return False
        for slice_id, frames in target.keyframe_map.items():
            for frame in frames:
                if frame.get("quality_score") is not None:
                    return True
        return False
