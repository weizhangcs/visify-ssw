# apps/workflow/annotation/services/annotation_service.py
import logging
import uuid
from datetime import datetime
from typing import Any, List

from django.conf import settings

from ...common.baseJob import BaseJob
from ...transcoding.jobs import TranscodingJob
from ..schemas import SceneType  # noqa: F401
from ..schemas import (
    AiMetadata,
    DataOrigin,
    DialogueContent,
    DialogueItem,
    ItemContext,
    MediaAnnotation,
    SceneContent,
    SceneItem,
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
            # 仅加载核心业务字段 (id, dialogues, scenes/slices) 以降低内存峰值
            # 即使 slices 有 2.6MB，我们只加载它，而不加载可能同样巨大的 v
            material = Material.objects.filter(media=job.media).defer("keyframe_map", "tech_meta", "error_log").first()
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
                if material.dialogue:
                    media_anno.dialogues = AnnotationService._adapt_refinery_dialogues(material.dialogue)
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

        # (B) Transcoding Job (Legacy Fallback)
        if not video_url:
            try:
                tj = TranscodingJob.objects.filter(media=job.media, status="COMPLETED").order_by("-modified").first()
                if tj and tj.output_url:
                    video_url = AnnotationService._build_absolute_url(tj.output_url)
            except Exception:
                pass

        # (C) Raw Source
        if not video_url and job.media.source_video:
            video_url = AnnotationService._build_absolute_url(job.media.source_video.url)

        if video_url:
            media_anno.source_path = video_url

        # 3. 注入 Character List (辅助数据)
        # 无论冷热启动，都尝试刷新角色列表 (从 Asset 或 Refinery)
        media_anno.character_list = AnnotationService.get_character_roster(job.media)

        return media_anno

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

        # 1. [TODO] 优先从 Refinery Material.dialogue 中聚合
        # 目前 Refinery 产出的 dialogue 分散在各句中，尚未进行全剧聚类和归一化。
        # 未来计划：在 Refinery Pipeline 中增加 CharacterRefiner 步骤，
        # 产出结构化的角色表 (Material.character_map)，届时在此处优先读取。

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

            # 简单的类型映射，如果字符串不匹配，Schema 会 fallback 到 UNKNOWN
            raw_type = s_data.get("scene_type", "unknown")

            items.append(
                SceneItem(
                    start=s_data.get("start_time", 0.0),
                    end=s_data.get("end_time", 0.0),
                    content=SceneContent(
                        narrative_action=s_data.get("narrative_action", "未定义动作"),
                        label=s_data.get("narrative_action", "Scene")[:20],  # 简易截断作为标题
                        location=s_data.get("location"),
                        scene_type=raw_type,  # Pydantic 会尝试转换 Enum
                        visual_mood_tags=s_data.get("visual_mood_tags", []),
                        camera_logic=s_data.get("camera_logic"),
                        reason=s_data.get("reason"),
                        character_dynamics=s_data.get("character_dynamics"),
                        description="",
                    ),
                    context=ItemContext(id=str(uuid.uuid4()), origin=DataOrigin.AI_CV, is_verified=False),
                )
            )
        return items

    @staticmethod
    def save_annotation(job, payload: dict) -> MediaAnnotation:
        """
        [数据保存]
        前端提交 JSON -> Pydantic 校验 -> 覆盖保存
        """
        # 1. 校验
        try:
            annotation = MediaAnnotation(**payload)
        except Exception as e:
            logger.error(f"Validation Error: {e}")
            raise ValueError(f"Islinvalid Schema: {e}")

        # 2. 更新时间戳
        annotation.updated_at = datetime.now()

        # 3. 序列化
        # [Fix] JSONField 需要 dict 对象，而不是 JSON 字符串; mode='json' 确保 UUID/Date 等被正确转换
        data_dict = annotation.model_dump(mode="json", exclude_none=True)

        # 使用 Job 的轮转保存方法 (A/B Buffer)
        job.rotate_and_save(data_dict, save_to_db=True)

        # 更新状态为 PROCESSING (如果之前是 PENDING)
        if job.status == BaseJob.STATUS.PENDING:
            job.start_annotation()
            job.save()

        return annotation
