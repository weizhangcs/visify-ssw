import logging
import time

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
    3. handle_asset_barrier: 处理 Asset 级别的全局同步点 (Barrier)。
    """

    @classmethod
    def start_pipeline(cls, pipeline_id: str):
        """
        [Entry Point] 启动流水线：查找入口节点并点火。
        """
        from apps.atomflow.refinery.models import RefineryAtomPipeline

        try:
            pipeline = RefineryAtomPipeline.objects.select_related("rule").get(id=pipeline_id)

            # 1. 状态流转
            pipeline.status = RefineryAtomPipeline.Status.RUNNING
            # 启动时清空错误日志，以便记录新的错误
            pipeline.error_log = ""
            pipeline.save(update_fields=["status", "error_log"])

            logger.info(f"Starting pipeline {pipeline.name} ({pipeline.id})...")

            # 2. 解析规则，寻找入口 (无依赖的节点)
            rules_config = pipeline.rule.rules_config or []
            start_steps = []

            for step in rules_config:
                deps = step.get("dependence", [])
                if not deps:
                    start_steps.append(step)

            if not start_steps:
                logger.warning(f"No start steps found for pipeline {pipeline.id} in rule {pipeline.rule.name}")
                return

            # 3. 点火派发
            for step in start_steps:
                cls.dispatch(str(pipeline.id), step)

        except Exception as e:
            logger.error(f"Failed to start pipeline {pipeline_id}: {e}", exc_info=True)
            raise e

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
                if status in ["SUCCESS", "START", "WAITING"]:
                    continue

            # 2. 检查依赖
            deps = step.get("dependence", [])

            # [Fix] 仅触发依赖于当前步骤的后续节点 (DAG 逻辑)
            # 防止并行分支(如 Probe)完成时，错误地重复触发已由另一分支(如 HLS)触发的公共下游(如 Text)
            if current_seq not in deps:
                continue

            # 3. 验证所有依赖是否 SUCCESS
            dependencies_met = True
            for dep_seq in deps:
                dep_seq_str = str(dep_seq)
                if dep_seq_str not in metrics or metrics[dep_seq_str].get("status") != "SUCCESS":
                    dependencies_met = False
                    break

            # 4. 点火
            if dependencies_met:
                # [Barrier] 检查是否为 Asset 级别的聚合步骤
                if step.get("scope") == "ASSET":
                    logger.info(f"[Atomflow] Hit Asset Barrier: {step['name']} (Seq: {step['seq']})")
                    cls.handle_asset_barrier(pipeline, step)
                else:
                    logger.info(f"[Atomflow] Auto-dispatching next step: {step['name']} (Seq: {step['seq']})")
                    cls.dispatch(str(pipeline.id), step)

        # 5. [新增] 检查全流程是否结束
        # 如果所有定义的步骤都在 metrics 中标记为 SUCCESS，则认为 Pipeline 完成
        all_finished = True
        for step in rules_config:
            seq_str = str(step["seq"])
            if metrics.get(seq_str, {}).get("status") != "SUCCESS":
                all_finished = False
                break

        if all_finished:
            from apps.atomflow.refinery.models import RefineryAtomPipeline

            if pipeline.status != RefineryAtomPipeline.Status.SUCCESS:
                logger.info(f"Pipeline {pipeline.id} finished successfully.")
                pipeline.status = RefineryAtomPipeline.Status.SUCCESS
                pipeline.save(update_fields=["status"])

    @classmethod
    def handle_asset_barrier(cls, pipeline, step_config):
        """
        处理 Asset 级别的栅栏同步 (Barrier)。

        逻辑：
        1. 将当前 Pipeline 在该步骤的状态置为 WAITING。
        2. 检查同一 Asset 下的所有兄弟 Pipeline 是否都已到达该步骤 (WAITING 或 SUCCESS)。
        3. 如果全部到达，则触发一次聚合任务 (Reduce)。
        """
        from apps.atomflow.refinery.models import RefineryAtomPipeline

        seq = str(step_config["seq"])
        metrics = pipeline.metrics or {}

        # 1. 更新状态为 WAITING
        # 只有当状态不是 SUCCESS 时才更新 (防止重复进入)
        if metrics.get(seq, {}).get("status") != "SUCCESS":
            metrics[seq] = {"slug": step_config["unit_slug"], "status": "WAITING", "updated_at": time.time()}
            pipeline.metrics = metrics
            pipeline.save(update_fields=["metrics"])
            logger.info(f"Pipeline {pipeline.id} entered WAITING state for step {seq}")

        # 2. 检查兄弟节点
        try:
            # 假设链条: Pipeline -> Material -> Media -> Asset
            asset = pipeline.material.media.asset
            if not asset:
                # 孤立 Media，直接触发
                logger.info(f"Pipeline {pipeline.id} has no asset. Treating as single execution.")
                cls.trigger_asset_task(None, [str(pipeline.id)], step_config)
                return
        except AttributeError:
            logger.warning(f"Pipeline {pipeline.id} context missing (Material/Media/Asset).")
            return

        # 查找同一 Asset 下，且使用同一 Rule 的所有 Pipeline
        # 排除 FAILED 的 Pipeline，避免死锁 (策略可调整)
        siblings = RefineryAtomPipeline.objects.filter(material__media__asset=asset, rule=pipeline.rule).exclude(
            status="FAILED"
        )

        total_count = siblings.count()
        ready_count = 0
        pipeline_ids = []

        for p in siblings:
            pipeline_ids.append(str(p.id))
            p_metrics = p.metrics or {}
            s_status = p_metrics.get(seq, {}).get("status")
            if s_status in ["WAITING", "SUCCESS"]:
                ready_count += 1

        logger.info(
            f"Asset Barrier Check [{step_config['unit_slug']}]: {ready_count}/{total_count} ready. (Asset: {asset.title})"  # noqa: E501
        )

        # 3. 触发聚合任务
        if ready_count == total_count and total_count > 0:
            logger.info(f"Barrier Reached! Triggering asset task for {total_count} pipelines.")
            cls.trigger_asset_task(str(asset.id), pipeline_ids, step_config)

    @classmethod
    def trigger_asset_task(cls, asset_id, pipeline_ids, step_config):
        """
        发送聚合任务到队列。
        """
        celery_app.send_task(
            "apps.atomflow.refinery.tasks.execute_asset_step",
            args=[asset_id, pipeline_ids, step_config],
            queue="media_queue",
        )
