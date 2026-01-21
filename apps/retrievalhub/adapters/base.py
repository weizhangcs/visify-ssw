from abc import ABC, abstractmethod
from typing import Any, Dict, List

from apps.retrievalhub.schemas import RetrievalResult


class BaseAdapter(ABC):
    """
    检索适配器基类 (Adapter Pattern)。
    负责屏蔽底层数据源（Vector DB, SQL, API）的差异，提供统一的检索接口。
    """

    @abstractmethod
    def search(self, query: str, context: Dict[str, Any]) -> List[RetrievalResult]:
        """
        执行检索。

        Args:
            query: 用户查询字符串
            context: 上下文参数 (必须包含 'asset_id', 可选 'top_k', 'filters' 等)

        Returns:
            结构化结果列表 (RetrievalResult)。
        """
        pass
