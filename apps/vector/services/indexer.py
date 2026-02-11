# 文件路径: apps/vector/services/indexer.py

import json
import logging
from pathlib import Path
from typing import Dict, List

from django.conf import settings
from django.db import transaction

from apps.vector.models import VectorIndex
from apps.vector.services.embedding import EmbeddingService
from apps.vector.services.processor import DataProcessorService
from apps.vector.services.storage import VectorStorageService

logger = logging.getLogger(__name__)


class VectorIndexerService:
    """
    [Production Manager] 向量索引生产服务。
    负责调度完整的生产流程：清洗 -> 向量化 -> 建库 -> 资产注册。
    """

    @classmethod
    def build_and_register(cls, target_id: str, data_map: Dict[str, List[Dict]]):
        """
        为指定目标构建多模态索引。

        Args:
            target_id: 业务对象ID (如 Job ID)
            data_map: 数据字典 {'dialogue': [...], 'scene': [...]}
        """
        # 基础路径: media/vector_indices/{target_id}/
        base_path = Path(settings.MEDIA_ROOT) / "vector_indices" / str(target_id)
        base_path.mkdir(parents=True, exist_ok=True)

        for index_type, data_list in data_map.items():
            if not data_list:
                continue

            try:
                cls._process_single_type(target_id, index_type, data_list, base_path)
            except Exception as e:
                logger.error(f"Failed to build index {index_type} for {target_id}: {e}", exc_info=True)
                # 生产过程允许部分失败，记录日志即可，或者根据策略抛出

    @classmethod
    def _process_single_type(cls, target_id: str, index_type: str, data_list: List[Dict], base_path: Path):
        # 1. 精细化预处理 (Processor)
        corpus = []
        metadata = []
        debug_data = []  # [White-box] 用于存储源数据与语义文本的对照信息

        for item in data_list:
            text = DataProcessorService.extract_text(item, index_type)
            if text:
                corpus.append(text)
                # 构建轻量级元数据用于检索回溯
                meta = {
                    "id": item.get("id"),
                    "start": item.get("start_time") or item.get("timestamp", 0),
                    "end": item.get("end_time", 0),
                    "text_preview": text[:100],
                    "seq": item.get("sequence", 1),  # [New] 注入集数/序号，默认为 1
                }
                metadata.append(meta)

                # [White-box] 收集对照数据
                debug_data.append(
                    {
                        "item_id": item.get("id"),
                        "processed_text": text,  # 语义文本 (输入给 Embedding 模型的内容)
                        "source_data": item,  # 原始业务数据 (用于对照)
                    }
                )

        if not corpus:
            logger.warning(f"[{target_id}] No valid text extracted for {index_type}")
            return

        # [White-box] 保存调试文件 (JSON)
        # 路径示例: media/vector_indices/{job_id}/scene_debug.json
        try:
            debug_file = base_path / f"{index_type}_debug.json"
            with open(debug_file, "w", encoding="utf-8") as f:
                json.dump(debug_data, f, ensure_ascii=False, indent=2)
            logger.info(f"[{target_id}] Saved debug info to {debug_file}")
        except Exception as e:
            logger.warning(f"[{target_id}] Failed to save debug info: {e}")

        # 2. 向量化 (Embedding Engine)
        embeddings = EmbeddingService.encode(corpus)

        # 3. 物理存储 (Storage Infrastructure)
        file_name = f"{index_type}.index"
        abs_path = base_path / file_name

        VectorStorageService.build_and_save_index(embeddings, metadata, abs_path)

        # 4. 资产注册 (Asset Management)
        # 计算相对路径用于存储
        rel_path = str(abs_path.relative_to(settings.MEDIA_ROOT))

        with transaction.atomic():
            # 停用旧索引 (如果存在)
            VectorIndex.objects.filter(target_id=target_id, index_type=index_type).update(is_active=False)

            # 注册新索引
            VectorIndex.objects.create(
                target_id=target_id,
                index_type=index_type,
                file_path=rel_path,
                vector_count=len(corpus),
                dimension=embeddings.shape[1],
                model_name=EmbeddingService.MODEL_NAME,
                is_active=True,
            )

        logger.info(f"[{target_id}] Index {index_type} built and registered. Count: {len(corpus)}")
