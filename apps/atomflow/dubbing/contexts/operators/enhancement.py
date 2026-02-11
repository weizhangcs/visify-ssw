class AudioEnhancementContextMixin:
    def _payload_audio_enhancement(self, target):
        session_dir = self.media_root / "dubbing" / str(target.id)
        return {
            "vocals_path": str(self.media_root / target.stem_vocals),
            "mask_path": str(self.media_root / target.mask_gating_path)
            if getattr(target, "mask_gating_path", None)
            else target.gating_meta.get("mask_path"),
            "output_path": str(session_dir / "track_speech_enhanced.wav"),
        }

    def _handle_audio_enhancement(self, target, result):
        target.track_enhanced = self._relativize(result)

    def _check_audio_enhancement_ready(self, target):
        return bool(target.stem_vocals and target.gating_meta)

    def _check_audio_enhancement_done(self, target):
        return bool(target.track_enhanced)
