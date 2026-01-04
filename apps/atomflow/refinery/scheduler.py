import logging

from apps.common.atomflow.base_scheduler import BaseAtomScheduler
from visify_ssw.celery import app as celery_app

logger = logging.getLogger(__name__)


class RefineryAtomScheduler(BaseAtomScheduler):
    """
    [调度器] Refinery 专用原子调度器。

    负责根据 RefineryAtomRule 定义的规则，驱动 RefineryAtomPipeline 的执行。
    核心职责：
    1. dispatch: 将具体的原子任务发送到 Celery 队列。
    2. record_and_dispatch: 记录当前步骤结果，并根据依赖关系自动触发下一步。
    """

    @classmethod
    def dispatch(cls, target_id: str, step_config: dict):
        """
        点火：直接向指定队列发送任务。

        Args:
            target_id: 目标 Pipeline 的 ID (注意：不是 Material ID)。
            step_config: 规则配置中的单步配置 (包含 seq, unit_slug 等)。
        """
        # 传递 target_id 代替原本的 pipeline_id
        celery_app.send_task(
            "apps.atomflow.refinery.tasks.execute_step",
            args=[str(target_id), step_config["seq"], step_config["unit_slug"]],
            queue="media_queue",
        )

    @classmethod
    def record_and_dispatch(cls, pipe_ctx, current_seq, mode, **kwargs):
        """
        记录执行结果并驱动下一跳。

        通常在 Task 执行成功后调用。它会检查当前 Pipeline 的 Metrics，
        遍历规则配置，找出所有依赖已满足且尚未执行的步骤，自动进行派发。

        Args:
            pipe_ctx: 当前 Pipeline 上下文。
            current_seq: 刚完成的步骤序号。
            mode: 执行模式 (PROD/DEBUG)。
        """
        logger.info(f"Step {current_seq} finished in {mode} mode.")

        # 恢复自动点火逻辑
        # 在 PROD 模式下驱动后续流程

        pipeline = pipe_ctx.pipeline
        # 此时 pipeline 应该是最新的 (tasks.py 中已 refresh)
        metrics = pipeline.metrics or {}
        rules_config = pipeline.rule.rules_config

        # 遍历所有步骤，检查依赖是否满足
        for step in rules_config:
            step_seq_str = str(step["seq"])

            # 1. 跳过已执行或正在执行的步骤 (防止重复点火)
            if step_seq_str in metrics:
                status = metrics[step_seq_str].get("status")
                if status in ["SUCCESS", "START"]:
                    continue

            # 2. 检查依赖
            deps = step.get("dependence", [])
            # [Fix] 不要跳过无依赖的步骤 (如 text_analyze)
            # 如果它们尚未执行(metrics check passed)，说明是漏发的根节点，应当被补发

            # 3. 验证所有依赖是否 SUCCESS
            dependencies_met = True
            for dep_seq in deps:
                dep_seq_str = str(dep_seq)
                if dep_seq_str not in metrics or metrics[dep_seq_str].get("status") != "SUCCESS":
                    dependencies_met = False
                    break

            # 4. 点火
            if dependencies_met:
                logger.info(f"[Atomflow] Auto-dispatching next step: {step['name']} (Seq: {step['seq']})")
                cls.dispatch(str(pipeline.id), step)
