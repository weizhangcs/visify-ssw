# apps/workflow/annotation/services/annotation_service.py
import logging
import uuid
from datetime import datetime
from typing import Any, List

from django.conf import settings

from apps.common.schemas.annotation.workbench import AiMetadata, DataOrigin, DialogueContent, DialogueItem  # noqa: F401
from apps.common.schemas.annotation.workbench import HighlightType as WbHighlightType  # noqa: F401
from apps.common.schemas.annotation.workbench import (  # noqa: F401
    ItemContext,
    MediaAnnotation,
    SceneContent,
    SceneItem,
    SceneType,
)
from apps.common.schemas.narrative_dataset import CaptionItem as CommonCaptionItem
from apps.common.schemas.narrative_dataset import DialogueItem as CommonDialogueItem
from apps.common.schemas.narrative_dataset import HighlightItem as CommonHighlightItem
from apps.common.schemas.narrative_dataset import HighlightType as CommonHighlightType
from apps.common.schemas.narrative_dataset import (
    NarrativeChapter,
    NarrativeDataset,
    NarrativeScene,
    ProjectMetadata,
    SceneContentType,
)

logger = logging.getLogger(__name__)


class AnnotationService:
    @staticmethod
    def load_annotation(job) -> MediaAnnotation:
        """
        [数据加载与冷启动注入 - V4 Refinery Integration]
        1. 热启动: 直接读取 Job.data (JSONField)
        2. 冷启动: 从 Refinery Material 模型中读取并转义数据
        """
        media_anno = None

        # --- A. 热数据加载 (Hot Start) ---
        # 只要 data 字段不为空字典，就视为已有数据
        if job.data:
            try:
                # 直接从 JSONField 加载，无需文件 IO
                media_anno = MediaAnnotation(**job.data)
            except Exception as e:
                logger.error(f"Job {job.id}: Failed to parse existing job.data. Error: {e}")
                # 降级进入冷启动

        # --- B. 冷启动 (Cold Start) ---
        # 尝试获取关联的 Material
        material = None
        try:
            # 假设 Material 通过 media 外键关联，或者通过 pipeline 上下文查找
            # 这里使用最直接的假设：Material.media == job.media
            from apps.atomflow.refinery.models import Material

            # [Optimization] 使用 defer 推迟加载不需要的大字段 (如keyframe_map)
            # [Update] Slice 是 Refinery 的过程数据，Workbench 无需感知且数据量大，显式 defer
            # 仅加载核心业务字段 (id, dialogues, scenes) 以降低内存峰值
            material = Material.objects.filter(media=job.media).defer("keyframe_map", "tech_meta", "slices").first()
        except ImportError:
            logger.warning("Refinery Material model not found. Skipping Refinery injection.")
        except Exception as e:
            logger.warning(f"Failed to fetch Material for media {job.media.id}: {e}")

        # 如果没有热数据，则执行冷启动初始化
        if not media_anno:
            logger.info(f"Job {job.id}: Starting cold start initialization...")

            media_anno = MediaAnnotation(
                media_id=str(job.media.id),
                file_name=job.media.title,
                source_path="",  # 稍后统一注入
                duration=job.media.duration,
                sequence_number=job.media.sequence_number,
            )

            if material:
                if material.duration > 0:
                    media_anno.duration = material.duration

                # [核心适配] Refinery Material -> Annotation Schema
                logger.info(f"Refinery Material found (ID: {material.id}). Injecting tracks...")
                if material.dialogues:
                    media_anno.dialogues = AnnotationService._adapt_refinery_dialogues(material.dialogues)
                if material.scenes:
                    media_anno.scenes = AnnotationService._adapt_refinery_scenes(material.scenes)
            else:
                logger.warning("No Material data available. Job will start empty.")

        # =========================================================
        # [Asset Injection] 无论冷热启动，强制刷新静态资产 (URL, Waveform)
        # =========================================================

        # 1. 注入 Waveform (始终从 Material 获取最新)
        if material and material.waveform_data:
            wd = material.waveform_data
            if isinstance(wd, list):
                media_anno.waveform_data = wd
            elif isinstance(wd, dict) and "data" in wd:
                media_anno.waveform_data = wd["data"]

        # 2. 注入 Video URL (优先级: Material HLS > TranscodingJob > Source Video)
        video_url = ""

        # (A) Material HLS
        if material and material.hls_playlist:
            video_url = AnnotationService._build_absolute_url(material.hls_playlist)

        # (B) Raw Source (Fallback)
        if not video_url and job.media.source_video:
            video_url = AnnotationService._build_absolute_url(job.media.source_video.url)

        if video_url:
            media_anno.source_path = video_url

        # 3. 注入 Character List (辅助数据)
        # 无论冷热启动，都尝试刷新角色列表 (从 Asset 或 Refinery)
        media_anno.character_list = AnnotationService.get_character_roster(job.media)

        return media_anno

    @staticmethod
    def save_annotation(job, payload: dict, user_id: str = None) -> MediaAnnotation:
        """
        [数据保存]
        前端提交 JSON -> Pydantic 校验 -> 覆盖保存
        Service 层负责版本控制策略和状态流转的编排。
        """
        # 1. 校验
        try:
            annotation = MediaAnnotation(**payload)
        except Exception as e:
            logger.error(f"Validation failed for Job {job.id}: {e}")
            raise ValueError(f"数据校验失败: {e}")

        # 2. 序列化
        data_dict = annotation.model_dump(mode="json", exclude_none=True)

        # 3. 持久化 (调用 Job 的 A/B 轮转保存)
        job.rotate_and_save(data_dict, save_to_db=True)

        return annotation

    @staticmethod
    def _build_absolute_url(url: str) -> str:
        """统一处理 URL 前缀"""
        if not url:
            return ""
        if url.startswith("http"):
            return url
        base = getattr(settings, "LOCAL_MEDIA_URL_BASE", "").rstrip("/")
        path = url.lstrip("/")

        # [Fix] 自动补全 MEDIA_URL 前缀 (如 /media/)
        # 数据库中存储的通常是相对于 MEDIA_ROOT 的路径 (如 refinery/...)，需要拼接 MEDIA_URL 才能被 Nginx/Django 路由
        media_prefix = settings.MEDIA_URL.strip("/")
        if media_prefix and not path.startswith(f"{media_prefix}/"):
            path = f"{media_prefix}/{path}"

        return f"{base}/{path}"

    @staticmethod
    def get_character_roster(media) -> List[str]:
        """
        [辅助数据] 获取全剧角色列表 (用于前端 Inspector 自动补全)
        """
        character_set = set()

        # 1. [Refinery Integration] 优先从 Refinery Material.identified_characters 中聚合
        try:
            from apps.atomflow.refinery.models import Material

            # 只取 identified_characters 字段，减少 IO
            material = Material.objects.filter(media=media).only("identified_characters").first()

            if material and material.identified_characters:
                for char_item in material.identified_characters:
                    if isinstance(char_item, dict) and char_item.get("name"):
                        character_set.add(str(char_item.get("name")).strip())
        except Exception as e:
            logger.warning(f"Failed to load Material.identified_characters: {e}")

        # 2. 兜底：使用 Asset 预设的 known_characters
        try:
            if media.asset:
                known = getattr(media.asset, "known_characters", [])
                if isinstance(known, list):
                    character_set.update([str(n).strip() for n in known if n])
        except Exception as e:
            logger.warning(f"Failed to load asset.known_characters: {e}")

        return sorted(list(character_set))

    @staticmethod
    def _adapt_refinery_dialogues(refinery_dialogues: List[Any]) -> List[DialogueItem]:
        """
        [适配器] 将 Refinery 的 SubtitleItem 列表转换为 Workbench 的 DialogueItem 列表
        """
        items = []
        for d in refinery_dialogues:
            # 兼容 Pydantic 对象或 Dict
            d_data = d.model_dump() if hasattr(d, "model_dump") else d

            items.append(
                DialogueItem(
                    start=d_data.get("start_time", 0.0),
                    end=d_data.get("end_time", 0.0),
                    content=DialogueContent(
                        text=d_data.get("content", ""),
                        speaker=d_data.get("speaker", "Unknown"),
                        original_text=d_data.get("content", ""),  # 暂用 content 作为 original
                    ),
                    context=ItemContext(
                        id=str(uuid.uuid4()),
                        origin=DataOrigin.AI_LLM,
                        is_verified=False,
                        ai_meta=AiMetadata(
                            reasoning=d_data.get("reasoning"),
                            # voice_mood=d_data.get('voice_mood') # 如果 Schema 支持可加
                        ),
                    ),
                )
            )
        return items

    @staticmethod
    def _adapt_refinery_scenes(refinery_scenes: List[Any]) -> List[SceneItem]:
        """
        [适配器] 将 Refinery 的 Scene 对象转换为 Workbench 的 SceneItem
        """
        items = []
        for s in refinery_scenes:
            s_data = s.model_dump() if hasattr(s, "model_dump") else (s if isinstance(s, dict) else {})

            # [Fix] 适配 Refinery 嵌套结构: 业务字段可能位于 'content' 键下
            # 结构示例: { "start_time": 100, "content": { "narrative_action": "...", ... } }
            business_source = s_data.get("content") if isinstance(s_data.get("content"), dict) else s_data

            # 简单的类型映射，如果字符串不匹配，Schema 会 fallback 到 UNKNOWN
            raw_type_data = business_source.get("scene_type")
            if isinstance(raw_type_data, dict):
                raw_type = raw_type_data.get("value", "unknown")
            else:
                raw_type = str(raw_type_data) if raw_type_data else "unknown"

            items.append(
                SceneItem(
                    start=s_data.get("start_time", 0.0),
                    end=s_data.get("end_time", 0.0),
                    content=SceneContent(
                        narrative_action=business_source.get("narrative_action", "未定义动作"),
                        label=business_source.get("narrative_action", "Scene")[:20],  # 简易截断作为标题
                        location=business_source.get("location"),
                        scene_type=raw_type,  # Pydantic 会尝试转换 Enum
                        visual_mood_tags=business_source.get("visual_mood_tags", []),
                        camera_logic=business_source.get("camera_logic"),
                        reason=business_source.get("reason"),
                        character_dynamics=business_source.get("character_dynamics"),
                        description="",
                    ),
                    context=ItemContext(id=str(uuid.uuid4()), origin=DataOrigin.AI_CV, is_verified=False),
                )
            )
        return items

    @staticmethod
    def _format_seconds_to_timestamp(seconds: float) -> str:
        """辅助：秒 -> HH:MM:SS.mmm"""
        if seconds is None:
            seconds = 0.0
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return "{:02d}:{:02d}:{:06.3f}".format(int(h), int(m), s)

    @staticmethod
    def _map_scene_type(wb_type: Any) -> SceneContentType:
        """[映射] Workbench SceneType -> Narrative SceneContentType"""
        # 尝试直接值匹配
        try:
            val = wb_type.value if hasattr(wb_type, "value") else str(wb_type)
            return SceneContentType(val)
        except ValueError:
            pass

        # 模糊/特定映射
        val_lower = str(val).lower()
        mapping = {
            "dialogue": SceneContentType.DIALOGUE_HEAVY,
            "action": SceneContentType.ACTION,
            "montage": SceneContentType.MONTAGE,
            "establishing": SceneContentType.ESTABLISHING_SHOT,
            "emotional": SceneContentType.UNKNOWN,  # Narrative Schema 暂无 Emotional
        }
        return mapping.get(val_lower, SceneContentType.UNKNOWN)

    @staticmethod
    def _map_highlight_type(wb_type: Any) -> CommonHighlightType:
        """[映射] Workbench HighlightType -> Narrative HighlightType"""
        try:
            val = wb_type.value if hasattr(wb_type, "value") else str(wb_type)
            return CommonHighlightType(val)
        except ValueError:
            pass

        val_lower = str(val).lower()
        mapping = {
            "humor": CommonHighlightType.COMEDY,  # Humor -> Comedy
            "dialogue": CommonHighlightType.OTHER,  # Narrative 无 Dialogue 高光
            "information": CommonHighlightType.OTHER,
        }
        return mapping.get(val_lower, CommonHighlightType.OTHER)

    @staticmethod
    def generate_narrative_dataset(project) -> NarrativeDataset:
        """
        [数据组装] 构建 Narrative Dataset (原 Blueprint)
        将 Workbench 的工程数据 (MediaAnnotation) 转换为 下游消费数据 (NarrativeDataset)。
        """
        try:
            valid_jobs = project._get_valid_jobs()

            scenes_map = {}
            chapters_map = {}

            # [Fix] 全局场景计数器，用于生成线性递增的 local_id (1, 2, 3...)
            global_scene_counter = 1

            # 1. 遍历 Job，转换数据
            for job in valid_jobs:
                media_anno = AnnotationService.load_annotation(job)

                # 1.1 构建 Chapter (对应一个 Media)
                # 注意：NarrativeDataset 的 Chapter 结构比较简单，主要作为索引
                chapter_uuid = uuid.UUID(media_anno.media_id) if media_anno.media_id else uuid.uuid4()
                chapter_scene_ids = []

                # 1.2 转换 Scenes
                for s_item in media_anno.scenes:
                    # 生成 Scene UUID (优先使用 context.id)
                    try:
                        s_uuid = uuid.UUID(s_item.context.id)
                    except:  # noqa: E722
                        s_uuid = uuid.uuid4()

                    # 映射 SceneContentType
                    content_type = AnnotationService._map_scene_type(s_item.content.scene_type)

                    # 映射 Dialogues
                    common_dialogues = []
                    for d in media_anno.dialogues:
                        # 简单的包含关系判断：对白时间在场景范围内
                        if s_item.start <= d.start < s_item.end:
                            common_dialogues.append(
                                CommonDialogueItem(
                                    content=d.content.text,
                                    speaker=d.content.speaker,
                                    start_time=AnnotationService._format_seconds_to_timestamp(d.start),
                                    end_time=AnnotationService._format_seconds_to_timestamp(d.end),
                                )
                            )

                    # 映射 Captions & Highlights (逻辑同上)
                    common_captions = []
                    for c in media_anno.captions:
                        if s_item.start <= c.start < s_item.end:
                            common_captions.append(
                                CommonCaptionItem(
                                    content=c.content.content,
                                    type="Other",  # CaptionType 暂未在 Narrative 中定义复杂 Enum，保持 Other 或扩展
                                    start_time=AnnotationService._format_seconds_to_timestamp(c.start),
                                    end_time=AnnotationService._format_seconds_to_timestamp(c.end),
                                )
                            )

                    common_highlights = []
                    for h in media_anno.highlights:
                        if s_item.start <= h.start < s_item.end:
                            # 将 mood 放入 tags
                            tags = []
                            if h.content.mood:
                                tags.append(
                                    h.content.mood.value if hasattr(h.content.mood, "value") else str(h.content.mood)
                                )

                            common_highlights.append(
                                CommonHighlightItem(
                                    description=h.content.description or "",
                                    type=AnnotationService._map_highlight_type(h.content.type),
                                    start_time=AnnotationService._format_seconds_to_timestamp(h.start),
                                    end_time=AnnotationService._format_seconds_to_timestamp(h.end),
                                    tags=tags,
                                )
                            )

                    # 构建 NarrativeScene
                    # [Fix] 使用全局线性递增 ID，而非基于章节的偏移量
                    scene_local_id = global_scene_counter
                    global_scene_counter += 1

                    narrative_scene = NarrativeScene(
                        scene_uuid=s_uuid,
                        id=scene_local_id,
                        start_time=AnnotationService._format_seconds_to_timestamp(s_item.start),
                        end_time=AnnotationService._format_seconds_to_timestamp(s_item.end),
                        scene_content_type=content_type,
                        # [Fix] 补全核心叙事与运镜分析
                        narrative_summary=s_item.content.narrative_action,
                        camera_movement=s_item.content.camera_logic or "",
                        dialogues=common_dialogues,
                        captions=common_captions,
                        highlights=common_highlights,
                        inferred_location=s_item.content.location or "Unknown",
                        character_dynamics=s_item.content.character_dynamics or "",
                        mood_and_atmosphere=",".join(s_item.content.visual_mood_tags),
                    )

                    scenes_map[str(s_uuid)] = narrative_scene
                    chapter_scene_ids.append(str(s_uuid))

                # 构建 Chapter
                chapter = NarrativeChapter(
                    chapter_uuid=chapter_uuid,
                    local_id=media_anno.sequence_number,
                    name=media_anno.file_name,
                    scene_ids=chapter_scene_ids,
                )
                chapters_map[str(chapter_uuid)] = chapter

            # 2. 构建 Metadata
            metadata = ProjectMetadata(
                asset_name=project.asset.title if project.asset else "Unknown Asset",
                project_name=project.name,
                version="1.0",
                issue_date=datetime.now().isoformat(),
                annotator="Annotation Workbench",
                description=project.description or "",
            )

            # 3. 构建 Dataset
            dataset = NarrativeDataset(
                asset_uuid=project.asset.id if project.asset else uuid.uuid4(),
                project_uuid=project.id,
                project_metadata=metadata,
                scenes=scenes_map,
                chapters=chapters_map,
            )

            # 4. 持久化 (BLUEPRINT)
            project.save_artifact(
                "BLUEPRINT",
                dataset.model_dump_json(
                    indent=2,
                    by_alias=True,
                    exclude={"scenes": {"__all__": {"start_sec", "end_sec", "duration"}}},
                ),
            )

            return dataset

        except Exception as e:
            logger.error(f"Generate Narrative Dataset failed for Project {project.id}: {e}", exc_info=True)
            raise e
