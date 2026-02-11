import logging

logger = logging.getLogger(__name__)


class VideoOCRContextMixin:
    def _payload_video_ocr(self, target):
        # [Fix] 强制刷新对象，防止因 Celery 序列化导致读取到旧的数据库状态
        # 确保能获取到刚刚由 Gating 步骤写入的 mask_gating_path
        target.refresh_from_db()

        session_dir = self.media_root / "dubbing" / str(target.id)
        input_file = self.media_root / target.material.media.source_video.name

        mask_path = None
        if getattr(target, "mask_gating_path", None):
            mask_path = str(self.media_root / target.mask_gating_path)
            logger.info(f"OCR Payload: Found gating mask at {mask_path}")
        else:
            logger.info(f"OCR Payload: No gating mask found for target {target.id}. Running without audio filtering.")

        return {"input_path": str(input_file), "output_dir": str(session_dir), "mask_path": mask_path}

    def _handle_video_ocr(self, target, result):
        target.ocr_csv_path = self._relativize(result[0])

    def _check_video_ocr_ready(self, target):
        return bool(target.material and target.material.media.source_video)

    def _check_video_ocr_done(self, target):
        return bool(target.ocr_csv_path)
