from ...schemas import MultimodalSlice


class SlicingContextMixin:
    """
    Context Mixin for visual slicing.

    Provides methods to generate payloads for and handle results from the SlicingService.
    """

    def _payload_slicing(self, target):
        """
        Generate payload for the SlicingService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the proxy video path, duration, dialogue track,
            and waveform data needed for slicing logic.
        """
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel
        return {
            "proxy_path": str(abs_proxy_path),
            "duration": target.duration,
            "dialogue_track": target.dialogue_track,
            "waveform_data": target.waveform_data,
        }

    def _handle_slicing(self, target, result):
        """
        Handle the result from the SlicingService.

        Updates the Material's visual_slices with the generated slice list.

        Args:
            target: The Material instance.
            result: A dictionary containing a list of 'slices'.
        """
        raw_slices = result.get("slices", [])
        target.visual_slices = [MultimodalSlice(**s).model_dump() for s in raw_slices]

    def _check_slicing_ready(self, target):
        """
        Check if the Slicing task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if proxy video and dialogue track exist, False otherwise.
        """
        return bool(target.proxy_video) and bool(target.dialogue_track)

    def _check_slicing_done(self, target):
        """
        Check if the Slicing task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if visual_slices is populated, False otherwise.
        """
        return bool(target.visual_slices)
