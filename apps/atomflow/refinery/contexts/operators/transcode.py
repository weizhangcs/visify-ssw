from pathlib import Path


class TranscodeContextMixin:
    def _payload_transcode(self, target):
        source_path = Path(target.media.source_video.path)
        rel_path = f"refinery/{target.id}/proxy.mp4"
        abs_output_path = self.media_root / rel_path

        return {"source_path": str(source_path), "output_path": str(abs_output_path), "rel_path": rel_path}

    def _handle_transcode(self, target, result):
        target.proxy_video = result.get("rel_path")

    def _check_transcode_ready(self, target):
        return bool(target.media.source_video)

    def _check_transcode_done(self, target):
        return bool(target.proxy_video)
