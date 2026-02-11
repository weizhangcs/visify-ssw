class AudioGatingContextMixin:
    def _payload_audio_gating(self, target):
        session_dir = self.media_root / "dubbing" / str(target.id)
        return {"vocals_path": str(self.media_root / target.stem_vocals), "output_base": str(session_dir)}

    def _handle_audio_gating(self, target, result):
        target.gating_meta = result
        if result.get("mask_path"):
            target.mask_gating_path = self._relativize(result["mask_path"])

    def _check_audio_gating_ready(self, target):
        return bool(target.stem_vocals)

    def _check_audio_gating_done(self, target):
        return bool(target.gating_meta)
