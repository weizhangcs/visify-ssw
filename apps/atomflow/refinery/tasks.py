import time

from celery import shared_task

from apps.atomflow.refinery.contexts.atomic import RefineryAtomicContext
from apps.atomflow.refinery.contexts.pipeline import RefineryPipelineContext
from apps.atomflow.refinery.scheduler import RefineryAtomScheduler
from apps.atomflow.refinery.task_registry import dispatch_asset_service_adapter, dispatch_service_adapter


@shared_task(bind=True, name="apps.atomflow.refinery.tasks.execute_step")
def refinery_atomic_task(self, pipeline_id, seq, op_slug):
    """
    [Task] Refinery 原子任务执行入口。

    遵循 Atomflow 标准范式：
    1. Context Isolation: 初始化 Pipeline 和 Atomic 上下文。
    2. Payload Extraction: 从 Atomic Context 获取纯净输入数据。
    3. Execution: 调用 _dispatch_service 分发到具体的 Service 执行。
    4. Result Handling: 将结果回填至 Atomic Context。
    5. Scheduling: 记录 Metrics 并驱动 Scheduler 进行下一跳。

    Args:
        pipeline_id: 当前执行的 Pipeline ID。
        seq: 当前步骤在规则中的序号。
        op_slug: 算子标识符 (如 transcode, probe)。
    """
    pipe_ctx = RefineryPipelineContext(pipeline_id)
    # 修正：RefineryPipelineContext.pipeline.target_id 是 CharField，但我们需要传递给 AtomicContext
    # AtomicContext 内部会处理 target_id
    target_id = pipe_ctx.pipeline.target_id
    atomic_ctx = RefineryAtomicContext(target_id)

    # 记录开始状态，传入 slug
    start_time = time.time()
    pipe_ctx.transit_state(seq, op_slug, "START")

    try:
        # A. 转换：获取 Payloads
        payload = atomic_ctx.get_payload(op_slug)

        # B. 执行：分发到具体的 Service 并适配参数
        result = dispatch_service_adapter(op_slug, payload, target_id)

        # C. 驱动：回填业务数据
        atomic_ctx.handle_result(op_slug, result)

        # [Fix] 强制刷新 Pipeline 状态
        # atomic_ctx.handle_result 更新了数据库中的 metrics (SUCCESS)
        # 但 pipe_ctx.pipeline 实例中的 metrics 仍然是旧的 (START)
        # Scheduler 依赖最新的 metrics 来判断依赖关系，否则无法触发下一步
        pipe_ctx.pipeline.refresh_from_db()

        # D. 结果回流至 Scheduler
        duration = time.time() - start_time
        # record_and_dispatch 内部会自动 transit_state(seq, "SUCCESS")
        # [Fix] mode 属性在 rule 上，不在 pipeline 上
        RefineryAtomScheduler.record_and_dispatch(
            pipe_ctx=pipe_ctx, current_seq=seq, mode=pipe_ctx.pipeline.rule.mode, duration=duration
        )

    except Exception as e:
        # 记录失败状态，传入 slug
        pipe_ctx.transit_state(seq, op_slug, "FAIL", error_msg=str(e))

        # [Optimization] 如果是 413 (Payload Too Large) 或 400-499 客户端错误，重试无意义，直接抛出失败
        error_str = str(e)
        if "413" in error_str or "Client Error" in error_str:
            raise e

        raise self.retry(exc=e)


@shared_task(bind=True, name="apps.atomflow.refinery.tasks.execute_asset_step")
def execute_asset_step(self, asset_id, pipeline_ids, step_config):
    """
    [Task] Asset 级别聚合任务执行入口 (Barrier/Reduce)。

    职责：
    1. 执行聚合逻辑 (如 Global Character Refine)。
    2. 更新所有涉及 Pipeline 的状态为 SUCCESS。
    3. 唤醒所有 Pipeline 继续执行 (Resume)。
    """
    from apps.atomflow.refinery.models import RefineryAtomPipeline

    op_slug = step_config["unit_slug"]
    seq = step_config["seq"]

    # 1. 执行聚合业务逻辑
    try:
        dispatch_asset_service_adapter(op_slug, asset_id, pipeline_ids, step_config)
    except Exception as e:
        # 如果聚合失败，所有 Pipeline 标记为 FAIL
        # 或者只标记当前 Task 失败，等待重试
        raise self.retry(exc=e)

    # 2. 唤醒所有 Pipeline (Resume)
    pipelines = RefineryAtomPipeline.objects.filter(id__in=pipeline_ids)

    for pipeline in pipelines:
        # 更新 Metrics 为 SUCCESS
        metrics = pipeline.metrics or {}
        metrics[str(seq)] = {"slug": op_slug, "status": "SUCCESS", "finished_at": time.time()}
        pipeline.metrics = metrics
        pipeline.save(update_fields=["metrics"])

        # 驱动下一跳
        pipe_ctx = RefineryPipelineContext(str(pipeline.id))
        RefineryAtomScheduler.record_and_dispatch(
            pipe_ctx=pipe_ctx, current_seq=seq, mode=pipeline.rule.mode, duration=0  # 聚合任务耗时难以分摊，暂记0
        )
