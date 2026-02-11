class VideoInpaintingContextMixin:
    def _payload_video_inpainting(self, target):
        session_dir = self.media_root / "dubbing" / str(target.id)
        # [Fix] 使用源视频进行去字幕，确保画质无损
        input_file = self.media_root / target.material.media.source_video.name
        return {
            "input_path": str(input_file),
            "ocr_csv_path": str(self.media_root / target.ocr_csv_path),
            "output_path": str(session_dir / "video_clean.mp4"),
        }

    def _handle_video_inpainting(self, target, result):
        target.video_clean = self._relativize(result)

    def _check_video_inpainting_ready(self, target):
        return bool(target.ocr_csv_path)

    def _check_video_inpainting_done(self, target):
        return bool(target.video_clean)
