from pathlib import Path


class TranscodeContextMixin:
    """
    Context Mixin for video transcoding.

    Provides methods to generate payloads for and handle results from the TranscodeService.
    """

    def _payload_transcode(self, target):
        """
        Generate payload for the TranscodeService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the source video path, the absolute output path
            for the transcoded file, and the relative path for database storage.
        """
        source_path = Path(target.media.source_video.path)
        rel_path = f"refinery/{target.id}/proxy.mp4"
        abs_output_path = self.media_root / rel_path

        return {"source_path": str(source_path), "output_path": str(abs_output_path), "rel_path": rel_path}

    def _handle_transcode(self, target, result):
        """
        Handle the result from the TranscodeService.

        Args:
            target: The Material instance.
            result: A dictionary containing the relative path of the transcoded video.
        """
        target.proxy_video = result.get("rel_path")

    def _check_transcode_ready(self, target):
        """
        Check if the Transcode task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if a source video exists, False otherwise.
        """
        return bool(target.media.source_video)

    def _check_transcode_done(self, target):
        """
        Check if the Transcode task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if a proxy video path is set, False otherwise.
        """
        return bool(target.proxy_video)
