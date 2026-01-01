import logging

from apps.common.atomflow.base_scheduler import BaseAtomScheduler
from visify_ssw.celery import app as celery_app

logger = logging.getLogger(__name__)


class RefineryAtomScheduler(BaseAtomScheduler):
    @classmethod
    def dispatch(cls, target_id: str, step_config: dict):
        """
        点火：直接向指定队列发送任务
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
        记录执行结果并驱动下一跳
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
