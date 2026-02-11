import time

from celery import shared_task

from apps.atomflow.dubbing.contexts.atomic import DubbingAtomicContext
from apps.atomflow.dubbing.contexts.pipeline import DubbingPipelineContext
from apps.atomflow.dubbing.scheduler import DubbingAtomScheduler
from apps.atomflow.dubbing.task_registry import dispatch_service_adapter


@shared_task(bind=True, name="apps.atomflow.dubbing.tasks.execute_dubbing_step")
def execute_dubbing_step(self, pipeline_id, seq, op_slug):
    """
    Dubbing 原子任务入口
    """
    pipe_ctx = DubbingPipelineContext(pipeline_id)
    target_id = pipe_ctx.pipeline.target_id
    atomic_ctx = DubbingAtomicContext(target_id)

    start_time = time.time()
    pipe_ctx.transit_state(seq, op_slug, "START")

    try:
        # 1. 获取 Payload
        payload = atomic_ctx.get_payload(op_slug)

        # 2. 执行服务
        result = dispatch_service_adapter(op_slug, payload, target_id)

        # 3. 处理结果
        atomic_ctx.handle_result(op_slug, result)
        pipe_ctx.pipeline.refresh_from_db()

        # 4. 调度下一跳
        duration = time.time() - start_time
        DubbingAtomScheduler.record_and_dispatch(
            pipe_ctx, seq, pipe_ctx.pipeline.rule.mode, slug=op_slug, duration=duration
        )

    except Exception as e:
        pipe_ctx.transit_state(seq, op_slug, "FAIL", error_msg=str(e))
        raise self.retry(exc=e)
