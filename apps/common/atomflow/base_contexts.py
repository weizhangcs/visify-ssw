import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from django.db import transaction


class BasePipelineContext(ABC):
    """
    [流程上下文]
    职责：管理 AtomPipeline 的生命周期，隔离调度引擎与数据库
    """

    def __init__(self, pipeline_id: Any):
        self.pipeline_id = pipeline_id
        self._pipeline_instance = None

    @abstractmethod
    def get_pipeline_instance(self) -> Any:
        """获取具体的 Pipeline 模型实例（如 RefineryPipeline）"""
        pass

    @property
    def pipeline(self):
        if not self._pipeline_instance:
            self._pipeline_instance = self.get_pipeline_instance()
        return self._pipeline_instance

    def get_history(self) -> Dict[str, Dict]:
        """
        获取已完成的 metrics，供 Scheduler 决策。
        返回格式: {"1": {"status": "SUCCESS"}, "2": {"status": "FAILED"}}
        """
        return self.pipeline.metrics or {}

    def get_rules_config(self) -> List[Dict]:
        """获取当前 Pipeline 关联的 rules_config 镜像"""
        # 实际实现中，通常从关联的 Rule 模型中读取
        return self.pipeline.rule.rules_config if hasattr(self.pipeline, "rule") else []

    @transaction.atomic
    def transit_state(self, seq: int, slug: str, event: str, duration: float = 0, error_msg: str = None):
        """
        [Handler] 驱动工程状态流展。
        event: START / SUCCESS / FAIL
        """
        metrics = self.pipeline.metrics or {}
        str_seq = str(seq)

        # 确保 metrics 中该 seq 的记录存在，并初始化/更新 slug
        if str_seq not in metrics:
            metrics[str_seq] = {}
        metrics[str_seq]["slug"] = slug

        if event == "START":
            self.pipeline.status = "RUNNING"
            metrics[str_seq].update({"status": "RUNNING", "start_at": time.time()})

        elif event == "SUCCESS":
            metrics[str_seq].update({"status": "SUCCESS", "duration": duration, "finished_at": time.time()})
            # 如果是最后一个 seq (基于 rules_config 判定)，可将 pipeline.status 设为 SUCCESS

        elif event == "FAIL":
            self.pipeline.status = "FAILED"
            self.pipeline.stop_point = seq
            self.pipeline.error_log = error_msg
            metrics[str_seq].update({"status": "FAILED", "error": error_msg, "finished_at": time.time()})

        self.pipeline.metrics = metrics
        self.pipeline.save(update_fields=["status", "metrics", "stop_point", "error_log"])


class BaseAtomicContext(ABC):
    """
    [业务上下文]
    职责：作为业务实体的 Facade，封装数据读写与行为（Handler）
    """

    def __init__(self, target_id: Any):
        self.target_id = target_id
        self._target_instance = None

    @abstractmethod
    def get_target_instance(self) -> Any:
        """获取具体的业务模型实例（如 Material）"""
        pass

    @property
    def target(self):
        if not self._target_instance:
            self._target_instance = self.get_target_instance()
        return self._target_instance

    # --- 数据加载 (供 Task 使用) ---
    @abstractmethod
    def get_payload(self, slug: str) -> Any:
        """根据算子的 slug，从实体中提取纯净的输入数据"""
        pass

    # --- 行为处理 (Handler) ---
    @abstractmethod
    def handle_result(self, slug: str, result: Any):
        """
        核心 Handler：负责将 Service 处理后的“结果”写回业务实体。
        这里可以包含复杂的逻辑，如：如果是字幕处理，则更新 dialogue_track。
        """
        pass

    # --- 状态判定 (原子能力检查) ---
    @abstractmethod
    def check_is_ready(self, slug: str) -> bool:
        """对应 Unit 的 is_ready，检查物理数据是否存在"""
        pass

    @abstractmethod
    def check_is_done(self, slug: str) -> bool:
        """对应 Unit 的 is_done，检查结果是否已实质性产生"""
        pass
