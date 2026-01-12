import logging

from apps.atomflow.refinery.schemas import Scene, SceneContent

logger = logging.getLogger(__name__)


class RegroupSliceContextMixin:
    """
    Context Mixin for scene clustering and summarization.

    Provides methods to generate payloads for and handle results from the SliceRegrouperService.
    """

    def _payload_regroup_slice(self, target):
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
        }

    def _handle_regroup_slice(self, target, result):
        """
        Handle the result from the SliceRegrouperService.

        Updates the Material's 'scenes' field with the generated scene list.

        Args:
            target: The Material instance.
            result: A dictionary containing the 'scenes' list.
        """
        scenes_data = result.get("scenes", [])
        if not scenes_data:
            return

            # [Adapter] Cloud returns scene_type as {"value": "...", "label": "..."}
            # Local Schema SceneContent.scene_type is now LabelItem, so it matches.
            # But we need to ensure Pydantic validation passes.

        validated_scenes = []
        for s in scenes_data:
            try:
                # Ensure content is validated against SceneContent
                content_obj = SceneContent(**s["content"])
                s["content"] = content_obj.model_dump()
                scene_obj = Scene(**s)
                validated_scenes.append(scene_obj.model_dump())
            except Exception as e:
                logger.warning(f"Failed to validate scene {s.get('scene_id')}: {e}")

        target.scenes = validated_scenes

    def _check_regroup_slice_ready(self, target):
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

    def _check_regroup_slice_done(self, target):
        """
        Check if the Slice Regrouper task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if the 'scenes' field is populated, False otherwise.
        """
        return bool(target.scenes)
