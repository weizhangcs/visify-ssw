from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseAtomScheduler(ABC):
    """
    [调度引擎范式]
    增加模式感知：控制自动化程度
    """

    @classmethod
    def get_next_runnable_steps(
        cls, history: Dict[str, Any], rules_config: List[Dict[str, Any]], mode: str = "PROD"  # 核心切换点
    ) -> List[Dict[str, Any]]:
        """
        决策算法：基于历史和规则计算候选集
        """
        # 1. 如果是 DEBUG 模式且 history 已经有运行中的记录，
        # 或者刚刚完成了一个任务，在某些场景下我们可能直接返回空，
        # 但更通用的做法是：Scheduler 依然算出“逻辑上”可运行的任务，
        # 而由 dispatch 逻辑根据 mode 来决定是否真正“点火”。

        runnable_steps = []

        # 获取已实质性完成的 seqs (SUCCESS 或 失败但 OPTIONAL)
        finished_seqs = {
            int(seq)
            for seq, meta in history.items()
            if meta.get("status") == "SUCCESS"
            or (meta.get("status") == "FAILED" and cls._is_optional(seq, rules_config))
        }

        for item in rules_config:
            curr_seq = item["seq"]

            # 已经成功过的跳过
            if str(curr_seq) in history and history[str(curr_seq)].get("status") == "SUCCESS":
                continue

            # 检查依赖
            dependence = item.get("dependence", [])
            if not dependence:
                runnable_steps.append(item)
            else:
                if all(dep in finished_seqs for dep in dependence):
                    runnable_steps.append(item)

        runnable_steps.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return runnable_steps

    @classmethod
    def record_and_dispatch(cls, pipe_ctx: Any, current_seq: int, mode: str, **kwargs):
        """
        [范式方法] 供 Task 完成时调用：记录当前，并决定是否点火下一跳
        """
        # 1. 记录当前步骤成功 (由 PipelineContext 处理)
        pipe_ctx.transit_state(current_seq, "SUCCESS", **kwargs)

        # 2. 模式判定：只有 PROD 模式才会自动寻找并触发下一跳
        if mode == "PROD":
            next_steps = cls.get_next_runnable_steps(
                history=pipe_ctx.get_history(), rules_config=pipe_ctx.get_rules_config(), mode=mode
            )

            for step in next_steps:
                # 触发异步任务
                cls.dispatch(pipe_ctx.target_id, step)
        else:
            # DEBUG 模式下，仅记录，不 dispatch
            # 这里可以 log 一个“断点暂停”的信息
            pass

    @classmethod
    @abstractmethod
    def dispatch(cls, target_id: Any, step_config: Dict[str, Any]):
        """具体下发 Celery 任务的实现"""
        pass

    @classmethod
    def _is_optional(cls, seq: str, rules_config: List[Dict]) -> bool:
        """检查某个 seq 是否是可选任务"""
        for item in rules_config:
            if str(item["seq"]) == str(seq):
                return item.get("obligation") == "OPTIONAL"
        return False
