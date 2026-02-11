class VisualAnalysisContextMixin:
    def _payload_visual_analysis(self, target):
        session_dir = self.media_root / "dubbing" / str(target.id)
        # [Fix] 使用源视频进行人脸分析，提升检测精度
        input_file = self.media_root / target.material.media.source_video.name
        return {
            "video_path": str(input_file),
            "output_dir": str(session_dir),
            "temp_dir": str(session_dir / "temp_visual"),
        }

    def _handle_visual_analysis(self, target, result):
        target.face_csv_path = self._relativize(result)

    def _check_visual_analysis_ready(self, target):
        return bool(target.material and target.material.media.source_video)

    def _check_visual_analysis_done(self, target):
        return bool(target.face_csv_path)
