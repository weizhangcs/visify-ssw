class AudioAnalyzeContextMixin:
    """
    Context Mixin for audio analysis.

    Provides methods to generate payloads for and handle results from the AudioAnalyzerService.
    """

    def _payload_audio_analyze(self, target):
        """
        Generate payload for the AudioAnalyzerService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the video path (for audio extraction) and
            the dialogue to be analyzed.
        """
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel

        return {
            "video_path": str(abs_proxy_path),
            "dialogue": target.dialogue,
        }

    def _handle_audio_analyze(self, target, result):
        """
        Handle the result from the AudioAnalyzerService.

        Updates the Material's dialogue with the audio analysis results.

        Args:
            target: The Material instance.
            result: A dictionary containing the updated 'dialogue'.
        """
        target.dialogue = result.get("dialogue", [])

    def _check_audio_analyze_ready(self, target):
        """
        Check if the Audio Analyze task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if proxy video and dialogue exist, False otherwise.
        """
        return bool(target.proxy_video) and bool(target.dialogue)

    def _check_audio_analyze_done(self, target):
        """
        Check if the Audio Analyze task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if at least one item in the dialogue has audio analysis data.
        """
        if not target.dialogue:
            return False
        # Check if at least one item has audio_analysis
        return any(item.get("audio_analysis") for item in target.dialogue)
