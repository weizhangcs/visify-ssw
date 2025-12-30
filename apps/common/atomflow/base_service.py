from abc import ABC, abstractmethod
from typing import Any


class BaseAtomService(ABC):
    """
    [纯算子基类]
    职责：只负责逻辑运算。不直接与 Context 或 DB 交互。
    """

    @staticmethod
    @abstractmethod
    def run(*args, **kwargs) -> Any:
        """
        数据由 Task 从 Context 中加载后传入。
        返回：处理后的结果数据或布尔值。
        """
        pass
