import logging
from typing import Any, Dict, List

from .adapters.structured import StructuredAdapter
from .adapters.vector import VectorAdapter
from .schemas import RetrievalResult

logger = logging.getLogger(__name__)


class RetrievalEngine:
    """
    [Domain Service] 检索与上下文组装引擎。
    Facade 模式：对外提供统一的 search 接口，内部调度不同的 Adapter。
    """

    def __init__(self):
        # 注册适配器
        self.vector_adapter = VectorAdapter()
        self.structured_adapter = StructuredAdapter()

    def search(self, query: str, context: Dict[str, Any]) -> List[RetrievalResult]:
        """
        统一检索入口。
        """
        mode = context.get("mode", "hybrid")
        results: List[RetrievalResult] = []

        # 1. 路由策略 (Router)
        if mode in ["hybrid", "vector_only"]:
            try:
                v_results = self.vector_adapter.search(query, context)
                results.extend(v_results)
            except Exception as e:
                logger.error(f"Vector search failed: {e}")

        if mode in ["hybrid", "structured_only"]:
            try:
                s_results = self.structured_adapter.search(query, context)
                results.extend(s_results)
            except Exception as e:
                logger.error(f"Structured search failed: {e}")

        # 2. 融合策略 (Merger)
        # 基于 Content ID 去重
        unique_map = {}
        for r in results:
            # 假设 content 都有 id 字段
            cid = getattr(r.content, "id", None)
            if not cid:
                continue

            # 如果 ID 冲突，保留分数高的
            if cid not in unique_map or r.score > unique_map[cid].score:
                unique_map[cid] = r

        # 排序
        sorted_results = sorted(unique_map.values(), key=lambda x: x.score, reverse=True)

        return sorted_results[: context.get("top_k", 20)]
