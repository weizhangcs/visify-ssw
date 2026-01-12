from pathlib import Path

from apps.atomflow.refinery.schemas import TechMeta


class ProbeContextMixin:
    """
    Context Mixin for media file probing.

    Provides methods to generate payloads for and handle results from the ProbeService.
    """

    @property
    def media_root(self) -> Path:
        raise NotImplementedError

    def _payload_probe(self, target):
        """
        Generate payload for the ProbeService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the absolute path to the proxy video
            and a temporary path for WAV extraction.
        """
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel
        temp_wav_path = Path(f"/tmp/atomflow_probe_{target.id}.wav")

        return {"proxy_path": str(abs_proxy_path), "temp_wav_path": str(temp_wav_path)}

    def _handle_probe(self, target, result):
        """
        Handle the result from the ProbeService.

        Updates the Material's duration, technical metadata, and waveform data.

        Args:
            target: The Material instance.
            result: A dictionary containing duration, tech_meta, and waveform_data.
        """
        target.duration = result.get("duration", 0.0)
        target.tech_meta = TechMeta(**result.get("tech_meta", {})).model_dump()
        target.waveform_data = result.get("waveform_data", [])

    def _check_probe_ready(self, target):
        """
        Check if the Probe task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if a proxy video exists, False otherwise.
        """
        return bool(target.proxy_video)

    def _check_probe_done(self, target):
        """
        Check if the Probe task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if the duration is greater than 0, False otherwise.
        """
        return target.duration > 0
