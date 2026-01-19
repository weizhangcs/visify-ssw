import logging
import pickle
import shutil
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

logger = logging.getLogger(__name__)

try:
    import faiss
except ImportError:
    faiss = None


class VectorStorageService:
    """
    [Infrastructure] 向量存储与检索底层服务
    只负责 FAISS 操作和文件 I/O，不关心业务数据内容。
    """

    # 简单的内存缓存: { file_path_str: {'mtime': float, 'metadata': list, 'index_obj': faiss_index} }
    _index_cache = {}

    @staticmethod
    def build_and_save_index(embeddings: np.ndarray, metadata: List[Dict[str, Any]], output_path: Path):
        """
        构建 FAISS 索引并保存到磁盘。

        Args:
            embeddings: 归一化后的向量数组 (numpy array)
            metadata: 与向量对应的元数据列表
            output_path: 输出文件路径 (.pkl)
        """
        if faiss is None:
            raise RuntimeError("缺少 faiss-cpu 依赖")

        if len(metadata) != len(embeddings):
            raise ValueError(f"Metadata count ({len(metadata)}) does not match embeddings count ({len(embeddings)})")

        d = embeddings.shape[1]
        # 使用 Inner Product (IP) 计算余弦相似度 (前提是向量已归一化)
        index = faiss.IndexFlatIP(d)
        index.add(embeddings)

        # 序列化保存
        # 使用临时文件原子写入
        temp_path = output_path.with_suffix(".tmp")

        # 序列化 C++ 对象
        serialized_index = faiss.serialize_index(index)

        payload = {
            "count": index.ntotal,
            "metadata": metadata,
            "faiss_index": serialized_index,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_path, "wb") as f:
            pickle.dump(payload, f)

        shutil.move(temp_path, output_path)
        logger.info(f"Saved vector index to {output_path} ({index.ntotal} vectors)")

    @classmethod
    def load_and_search(cls, index_path: Path, query_vector: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        加载索引并执行检索 (带缓存)。

        Args:
            index_path: 索引文件路径
            query_vector: 查询向量 (shape: 1, d)
            top_k: 返回结果数量

        Returns:
            结果列表，每个元素包含 metadata 和 _score
        """
        if faiss is None:
            raise RuntimeError("缺少 faiss-cpu 依赖")

        cached_entry = cls._get_cached_index(index_path)
        if not cached_entry:
            return []

        index = cached_entry["index_obj"]
        metadata = cached_entry["metadata"]

        # 检索
        # D: Distances (Scores), I: Indices
        if len(query_vector.shape) == 1:
            query_vector = query_vector.reshape(1, -1)

        D, I = index.search(query_vector, top_k)  # noqa : E741

        results = []
        # I[0] 是第一个查询向量的结果索引列表
        for rank, idx in enumerate(I[0]):
            if idx == -1:
                continue

            if idx < len(metadata):
                item = metadata[idx].copy()
                item["score"] = float(D[0][rank])
                results.append(item)

        return results

    @classmethod
    def _get_cached_index(cls, index_path: Path):
        path_str = str(index_path)
        if not index_path.exists():
            return None

        try:
            current_mtime = index_path.stat().st_mtime
        except OSError:
            return None

        cached = cls._index_cache.get(path_str)
        if cached and cached["mtime"] == current_mtime:
            return cached

        logger.debug(f"Loading index from disk: {path_str}")
        try:
            with open(index_path, "rb") as f:
                data = pickle.load(f)

            if "faiss_index" not in data or "metadata" not in data:
                logger.error(f"Invalid index file format: {path_str}")
                return None

            index_obj = faiss.deserialize_index(data["faiss_index"])

            cache_entry = {"mtime": current_mtime, "metadata": data["metadata"], "index_obj": index_obj}
            cls._index_cache[path_str] = cache_entry
            return cache_entry
        except Exception as e:
            logger.error(f"Failed to load index {path_str}: {e}")
            return None
