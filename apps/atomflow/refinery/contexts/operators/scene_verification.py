import logging

logger = logging.getLogger(__name__)


class SceneVerificationContextMixin:
    """
    Context Mixin for scene verification (debug operator).
    """

    def _payload_scene_verification(self, target):
        """
        Generate payload for SceneVerificationService.
        """
        # 优先使用 Proxy，其次使用 Source
        video_path = ""
        if target.proxy_video:
            video_path = str(self.media_root / target.proxy_video)
        elif target.media.source_video:
            video_path = target.media.source_video.path

        # 输出目录: media_root/debug/<material_id>/scenes
        output_dir = self.media_root / "debug" / str(target.id) / "scenes"

        return {
            "video_path": video_path,
            "scenes": target.scenes,
            "output_dir": str(output_dir),
        }

    def _handle_scene_verification(self, target, result):
        """
        Handle result: Log the output location.
        """
        count = result.get("count", 0)
        output_dir = result.get("output_dir", "")
        logger.info(f"Scene Verification: Generated {count} clips in {output_dir}")
