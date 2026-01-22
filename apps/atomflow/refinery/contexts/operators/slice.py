from pathlib import Path

from apps.common.schemas.dataset.schemas import Slice


class SliceContextMixin:
    """
    Context Mixin for visual slicing.

    Provides methods to generate payloads for and handle results from the SlicingService.
    """

    @property
    def media_root(self) -> Path:
        raise NotImplementedError

    def _payload_slice(self, target):
        """
        Generate payload for the SlicingService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the proxy video path, duration, dialogue,
            and waveform data needed for slicing logic.
        """
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel

        asset = getattr(target.media, "asset", None)
        lang = "zh"
        if asset and asset.language:
            lang = asset.language.split("-")[0]

        return {
            "proxy_path": str(abs_proxy_path),
            "duration": target.duration,
            "dialogues": target.dialogues,
            "waveform_data": target.waveform_data,
            "lang": lang,
        }

    def _handle_slice(self, target, result):
        """
        Handle the result from the SlicingService.

        Updates the Material's slices with the generated slice list.

        Args:
            target: The Material instance.
            result: A dictionary containing a list of 'slices'.
        """
        raw_slices = result.get("slices", [])
        target.slices = [Slice(**s).model_dump() for s in raw_slices]

    def _check_slice_ready(self, target):
        """
        Check if the Slicing task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if proxy video and dialogue exist, False otherwise.
        """
        return bool(target.proxy_video) and bool(target.dialogues)

    def _check_slice_done(self, target):
        """
        Check if the Slicing task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if slices is populated, False otherwise.
        """
        return bool(target.slices)
