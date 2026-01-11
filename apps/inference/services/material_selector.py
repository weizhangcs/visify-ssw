import logging
import pickle
import time
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings

try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
except ImportError:
    faiss = None
    np = None
    SentenceTransformer = None

from apps.atomflow.refinery.models import Material

logger = logging.getLogger(__name__)


class MaterialSelectorService:
    """
    [Inference Service] 素材选择器 (Local RAG)。

    职责：
    1. 加载 Material 对应的本地向量索引。
    2. 将自然语言 Query (解说词) 转化为向量。
    3. 在 FAISS 索引中检索最相关的 Top-K 切片。
    """

    # 必须与 Refinery 端保持一致
    MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self):
        self.model = self._load_model()

    @classmethod
    def _load_model(cls):
        """
        加载 Embedding 模型。
        优先尝试加载 Docker 镜像内预置的离线模型，以提高启动速度。
        """
        if SentenceTransformer is None:
            raise RuntimeError("缺少 sentence-transformers 依赖")

        # 1. 尝试 Docker 离线路径
        offline_path = Path("/app/local_models") / cls.MODEL_NAME
        if offline_path.exists():
            logger.info(f"MaterialSelector: Loading offline model from {offline_path}")
            return SentenceTransformer(str(offline_path))

        # 2. 回退到默认缓存路径 (自动下载/读取缓存)
        logger.info(f"MaterialSelector: Loading model from cache ({cls.MODEL_NAME})")
        return SentenceTransformer(cls.MODEL_NAME)

    def search(self, material_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        执行语义检索。

        Args:
            material_id: 精炼物料 ID (用于定位索引文件)。
            query: 查询文本 (解说词/描述)。
            top_k: 返回结果数量。

        Returns:
            候选切片列表 (包含 slice_id, score, duration 等元数据)。
        """
        start_time = time.time()

        # 1. 获取索引路径
        try:
            material = Material.objects.get(id=material_id)
        except Material.DoesNotExist:
            logger.error(f"Material {material_id} not found.")
            return []

        if not material.local_vector_index_path:
            logger.warning(f"Material {material_id} has no vector index.")
            return []

        index_abs_path = Path(settings.MEDIA_ROOT) / material.local_vector_index_path
        if not index_abs_path.exists():
            logger.error(f"Index file missing at {index_abs_path}")
            return []

        # 2. 加载索引 (反序列化)
        with open(index_abs_path, "rb") as f:
            data = pickle.load(f)

        metadata = data["metadata"]  # List[Dict]
        faiss_index = faiss.deserialize_index(data["faiss_index"])

        # 3. Query Embedding
        query_vec = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_vec)

        # 4. 向量检索
        # D: Distances (Scores), I: Indices
        D, I = faiss_index.search(query_vec, top_k)  # noqa: E741

        # 5. 结果组装
        results = []
        for rank, idx in enumerate(I[0]):
            if idx == -1:
                continue  # FAISS padding

            item = metadata[idx].copy()
            item["score"] = float(D[0][rank])  # 相似度分数
            results.append(item)

        duration = (time.time() - start_time) * 1000
        logger.info(f"MaterialSelector: Found {len(results)} candidates for '{query}' in {duration:.2f}ms")  # noqa:E231

        return results
