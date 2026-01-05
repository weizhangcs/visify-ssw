import logging

from ...schemas import Scene

logger = logging.getLogger(__name__)


class SliceRegrouperContextMixin:
    """
    Context Mixin for scene clustering and summarization.

    Provides methods to generate payloads for and handle results from the SliceRegrouperService.
    """

    def _payload_slice_regrouper(self, target):
        """
        Generate payload for the SliceRegrouperService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the rich slices list, language, and model name.
        """
        asset = getattr(target.media, "asset", None)
        lang = "zh"  # Default to Chinese
        if asset and asset.language:
            lang = asset.language.split("-")[0]

        return {
            "slices": target.slices,  # 传递富切片列表
            "lang": lang,
            "model_name": "models/gemini-2.5-flash",  # 默认使用长上下文模型
        }

    def _handle_slice_regrouper(self, target, result):
        """
        Handle the result from the SliceRegrouperService.

        Updates the Material's 'scenes' field with the generated scene list.

        Args:
            target: The Material instance.
            result: A dictionary containing the 'scenes' list.
        """
        scenes = result.get("scenes", [])
        # 确保回填的是 Scene 对象的 model_dump() 列表
        target.scenes = [Scene(**s).model_dump() for s in scenes]
        logger.info(f"SliceRegrouper: Successfully saved {len(scenes)} scenes to Material {target.id}.")

    def _check_slice_regrouper_ready(self, target):
        """
        Check if the Slice Regrouper task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if slices are populated and contain visual analysis data.
        """
        if not target.slices:
            return False
        # 检查至少有一个切片包含视觉分析数据 (表示 visual_analyzer 已完成 hydration)
        return any(s.get("visual_contents") for s in target.slices)

    def _check_slice_regrouper_done(self, target):
        """
        Check if the Slice Regrouper task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if the 'scenes' field is populated, False otherwise.
        """
        return bool(target.scenes)
