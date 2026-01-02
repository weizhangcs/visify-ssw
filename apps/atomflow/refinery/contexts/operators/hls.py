class HLSContextMixin:
    def _payload_hls(self, target):
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
        target.hls_playlist = result.get("rel_path")

    def _check_hls_ready(self, target):
        return bool(target.proxy_video)

    def _check_hls_done(self, target):
        return bool(target.hls_playlist)
