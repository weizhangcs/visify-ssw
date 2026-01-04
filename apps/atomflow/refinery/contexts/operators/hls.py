class HLSContextMixin:
    """
    Context Mixin for HLS (HTTP Live Streaming) generation.

    Provides methods to generate payloads for and handle results from the HLSService.
    """

    def _payload_hls(self, target):
        """
        Generate payload for the HLSService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the absolute path to the proxy video,
            the absolute output directory for HLS files, and the relative
            path to the master playlist for database storage.
        """
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel
        rel_dir = f"refinery/{target.id}/hls"
        abs_output_dir = self.media_root / rel_dir

        return {
            "proxy_path": str(abs_proxy_path),
            "output_dir": str(abs_output_dir),
            "rel_path": f"{rel_dir}/index.m3u8",
        }

    def _handle_hls(self, target, result):
        """
        Handle the result from the HLSService.

        Args:
            target: The Material instance.
            result: A dictionary containing the relative path to the HLS playlist.
        """
        target.hls_playlist = result.get("rel_path")

    def _check_hls_ready(self, target):
        """
        Check if the HLS task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if a proxy video exists, False otherwise.
        """
        return bool(target.proxy_video)

    def _check_hls_done(self, target):
        """
        Check if the HLS task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if the HLS playlist path is set, False otherwise.
        """
        return bool(target.hls_playlist)
