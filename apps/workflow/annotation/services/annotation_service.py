# apps/workflow/annotation/services/annotation_service.py

import json
import logging
import os
from datetime import datetime

from ...common.baseJob import BaseJob

# 引入 Schema 定义
from ..schemas import MediaAnnotation
from .parsers import parse_ass_content, parse_scene_json_content

logger = logging.getLogger(__name__)


class AnnotationService:
    @staticmethod
    def load_annotation(job) -> MediaAnnotation:
        """
        [数据加载与冷启动注入 - V2]
        支持 SRT/ASS 字幕注入 + JSON 场景注入
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
        logger.info(f"Job {job.id}: Starting cold start initialization...")

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
        # [核心升级] 注入逻辑
        # =========================================================

        # 1. 强制注入对白 (Character ASS)
        # 1. 强制注入对白 (MOCK ASS)
        try:
            mock_ass_path = "/app/media_root/character_annotation/outputs/2025/12/23/EP02_ai.ass"
            if os.path.exists(mock_ass_path):
                with open(mock_ass_path, "r", encoding="utf-8") as f:
                    raw_content = f.read()
                    # [诊断点] 打印原始文件的前 200 个字符，确认编码和内容是否正常
                    logger.info(f"MOCK ASS Sample: {raw_content[:200]!r}")

                    if raw_content.strip():
                        media_anno.dialogues = parse_ass_content(raw_content)
                        logger.info(f"MOCK ASS Parse Result Count: {len(media_anno.dialogues)}")
                    else:
                        logger.error("MOCK ASS file is EMPTY")
        except Exception as e:
            logger.error(f"MOCK ASS Error: {e}", exc_info=True)

        # 2. 强制注入场景 (MOCK JSON)
        try:
            mock_json_path = "/app/tests/testdata/scene_annotation_result_232.json"
            if os.path.exists(mock_json_path):
                with open(mock_json_path, "r", encoding="utf-8") as f:
                    raw_json = f.read()
                    # [诊断点] 打印 JSON 采样
                    logger.info(f"MOCK JSON Sample: {raw_json[:200]!r}")

                    if raw_json.strip():
                        media_anno.scenes = parse_scene_json_content(raw_json)
                        logger.info(f"MOCK JSON Parse Result Count: {len(media_anno.scenes)}")
        except Exception as e:
            logger.error(f"MOCK JSON Error: {e}", exc_info=True)

        logger.info(f"Final Count - Scenes: {len(media_anno.scenes)}, Dialogues: {len(media_anno.dialogues)}")
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

        # [修改] 使用 Job 的轮转保存方法，而不是直接 file.save
        # 这样每次保存都会自动生成一个 Backup
        job.rotate_and_save(json_content, save_to_db=True)

        # 更新状态为 PROCESSING (如果之前是 PENDING)
        if job.status == BaseJob.STATUS.PENDING:
            job.start_annotation()
            job.save()

        return annotation
