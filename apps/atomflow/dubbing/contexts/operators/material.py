class AudioMaterialContextMixin:
    def _payload_audio_material_build(self, target):
        session_dir = self.media_root / "dubbing" / str(target.id)
        return {
            "inst_path": str(self.media_root / target.stem_inst),
            "vocals_path": str(self.media_root / target.stem_vocals),
            "mask_path": str(self.media_root / target.mask_gating_path)
            if getattr(target, "mask_gating_path", None)
            else target.gating_meta.get("mask_path"),
            "enhanced_path": str(self.media_root / target.track_enhanced),
            "output_path": str(session_dir / "track_material_bg.wav"),
        }

    def _handle_audio_material_build(self, target, result):
        target.track_material = self._relativize(result)

    def _check_audio_material_build_ready(self, target):
        return bool(target.stem_inst and target.track_enhanced)

    def _check_audio_material_build_done(self, target):
        return bool(target.track_material)
