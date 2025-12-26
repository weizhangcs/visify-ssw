# apps/workflow/annotation/services/annotation_service.py
import json
import logging
from datetime import datetime

from ...character_annotation.models import CharacterAnnotationJob
from ...common.baseJob import BaseJob
from ...scene_annotation.models import SceneAnnotationJob
from ..schemas import MediaAnnotation
from .parsers import parse_ass_content, parse_scene_json_content

logger = logging.getLogger(__name__)


class AnnotationService:
    @staticmethod
    def load_annotation(job) -> MediaAnnotation:
        """
        [数据加载与冷启动注入 - V3 Real Data]
        动态加载 Character (ASS) 和 Scene (JSON) 的真实产出物。
        """
        # --- A. 热数据加载 (保持不变) ---
        if job.annotation_file:
            try:
                job.annotation_file.open("r")
                content = job.annotation_file.read()
                job.annotation_file.close()
                if isinstance(content, bytes):
                    content = content.decode("utf-8")
                data = json.loads(content)
                return MediaAnnotation(**data)
            except Exception as e:
                logger.error(f"Job {job.id}: Failed to load existing annotation. Error: {e}")
                # 降级进入冷启动

        # --- B. 冷启动 (Cold Start) ---
        logger.info(f"Job {job.id}: Starting cold start initialization with REAL upstream data...")

        # 1. 基础骨架
        source_path = ""
        if job.media.source_video:
            source_path = job.media.source_video.url

        media_anno = MediaAnnotation(
            media_id=str(job.media.id),
            file_name=job.media.title,
            source_path=source_path,
            duration=job.media.duration,
            sequence_number=job.media.sequence_number,
            waveform_url=job.media.waveform_data.url if job.media.waveform_data else None,
        )

        # =========================================================
        # [核心修复] 动态注入真实业务数据
        # =========================================================

        # 1. 注入对白 (From CharacterAnnotationJob)
        try:
            # 查找该 Media 下最新完成的角色标注任务
            char_job = (
                CharacterAnnotationJob.objects.filter(media=job.media, status=BaseJob.STATUS.COMPLETED)
                .order_by("-modified")
                .first()
            )

            if char_job and char_job.output_ass_file:
                try:
                    with char_job.output_ass_file.open("r") as f:
                        raw_content = f.read()
                        if isinstance(raw_content, bytes):
                            raw_content = raw_content.decode("utf-8", errors="ignore")

                        if raw_content.strip():
                            media_anno.dialogues = parse_ass_content(raw_content)
                            logger.info(
                                f"Injected {len(media_anno.dialogues)} dialogues from CharacterJob {char_job.id}"
                            )
                except Exception as e:
                    logger.error(f"Failed to read ASS file from CharacterJob {char_job.id}: {e}")
            else:
                logger.warning(
                    f"No completed CharacterAnnotationJob found for Media {job.media.id}. Dialogues will be empty."
                )

        except Exception as e:
            logger.error(f"Error injecting dialogues: {e}", exc_info=True)

        # 2. 注入场景 (From SceneAnnotationJob)
        try:
            # 查找该 Media 下最新完成的场景标注任务
            scene_job = (
                SceneAnnotationJob.objects.filter(media=job.media, status=BaseJob.STATUS.COMPLETED)
                .order_by("-modified")
                .first()
            )

            # SceneJob 的结果直接存储在 JSONField (result) 中
            if scene_job and scene_job.result:
                try:
                    # parse_scene_json_content 支持直接传入 Dict
                    media_anno.scenes = parse_scene_json_content(scene_job.result)
                    logger.info(f"Injected {len(media_anno.scenes)} scenes from SceneJob {scene_job.id}")
                except Exception as e:
                    logger.error(f"Failed to parse result from SceneJob {scene_job.id}: {e}")
            else:
                logger.warning(f"No completed SceneAnnotationJob found for Media {job.media.id}. Scenes will be empty.")

        except Exception as e:
            logger.error(f"Error injecting scenes: {e}", exc_info=True)

        return media_anno

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
            raise ValueError(f"Invalid Schema: {e}")

        # 2. 更新时间戳
        annotation.updated_at = datetime.now()

        # 3. 序列化
        json_content = annotation.model_dump_json(indent=2, exclude_none=True)

        # 使用 Job 的轮转保存方法 (A/B Buffer)
        job.rotate_and_save(json_content, save_to_db=True)

        # 更新状态为 PROCESSING (如果之前是 PENDING)
        if job.status == BaseJob.STATUS.PENDING:
            job.start_annotation()
            job.save()

        return annotation
