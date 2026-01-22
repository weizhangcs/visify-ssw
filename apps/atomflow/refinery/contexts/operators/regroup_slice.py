import logging
import uuid

from apps.common.schemas.dataset.schemas import Scene, SceneContent, SceneTypeLabel

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
            # [Phase 1] 注入 SSOT 对白数据
            "dialogues": target.dialogues,
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

        validated_scenes = []
        for i, s_data in enumerate(scenes_data):
            try:
                # [SSOT Adaptation] Payload DTO (Dict) -> Core Domain Model (Pydantic)
                # 目标：确保写入 Material 的数据严格符合 apps.common.schemas.dataset.schemas.Scene

                content_data = s_data.get("content", {})

                # 1. 适配 SceneType (Payload LabelValue -> Core SceneTypeLabel)
                st_payload = content_data.get("scene_type")
                st_core = None
                if isinstance(st_payload, dict):
                    st_core = SceneTypeLabel(value=st_payload.get("value"), label=st_payload.get("label"))

                # 2. 构建 Core Content
                core_content = SceneContent(
                    narrative_action=content_data.get("narrative_action"),
                    location=content_data.get("location"),
                    scene_type=st_core,
                    visual_mood_tags=content_data.get("visual_mood_tags", []),
                    camera_logic=content_data.get("camera_logic"),
                    character_dynamics=content_data.get("character_dynamics"),
                    reason=content_data.get("reason"),
                )

                # 3. 构建 Core Scene (生成 UUID, 映射 index)
                # Payload 'scene_id' 对应 Core 'index'
                idx = s_data.get("scene_id", i)

                core_scene = Scene(
                    id=str(uuid.uuid4()),
                    index=idx,
                    start_time=s_data.get("start_time"),
                    end_time=s_data.get("end_time"),
                    content=core_content,
                    slice_ids=s_data.get("slice_ids", []),
                )

                validated_scenes.append(core_scene.model_dump())
            except Exception as e:
                logger.warning(f"Failed to adapt scene index {i}: {e}")

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
