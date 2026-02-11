class AudioPerceptionContextMixin:
    def _payload_audio_perception_analyze(self, target):
        session_dir = self.media_root / "dubbing" / str(target.id)
        return {
            "audio_path": str(self.media_root / target.track_enhanced),
            "output_path": str(session_dir / "perception.json"),
        }

    def _handle_audio_perception_analyze(self, target, result):
        target.perception_meta = result
        # [Fix] 填充 track_perception。若为空，Fusion 步骤读取 audio_path 时会解析为 MediaRoot 目录，导致 IsADirectoryError
        target.track_perception = target.track_enhanced

    def _check_audio_perception_analyze_ready(self, target):
        return bool(target.track_enhanced)

    def _check_audio_perception_analyze_done(self, target):
        return bool(target.perception_meta)
