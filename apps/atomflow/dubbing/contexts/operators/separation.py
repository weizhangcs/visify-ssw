class AudioSeparationContextMixin:
    def _payload_audio_separation(self, target):
        session_dir = self.media_root / "dubbing" / str(target.id)
        input_file = self.media_root / target.material.media.source_video.name
        return {"input_path": str(input_file), "output_dir": str(session_dir)}

    def _handle_audio_separation(self, target, result):
        target.stem_vocals = self._relativize(result[0])
        target.stem_inst = self._relativize(result[1])

    def _check_audio_separation_ready(self, target):
        return bool(target.material and target.material.media.source_video)

    def _check_audio_separation_done(self, target):
        return bool(target.stem_vocals and target.stem_inst)
