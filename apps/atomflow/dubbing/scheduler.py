import logging

from apps.common.atomflow.base_scheduler import BaseAtomScheduler
from visify_ssw.celery import app as celery_app

logger = logging.getLogger(__name__)


class DubbingAtomScheduler(BaseAtomScheduler):
    """
    Dubbing 调度器
    """

    @classmethod
    def dispatch(cls, target_id: str, step_config: dict):
        logger.info(f"[DubbingScheduler] Dispatching task -> Target: {target_id}, Step: {step_config['unit_slug']}")
        celery_app.send_task(
            "apps.atomflow.dubbing.tasks.execute_dubbing_step",
            args=[str(target_id), step_config["seq"], step_config["unit_slug"]],
            queue="media_queue",  # 必须发送到 media_queue 以利用 GPU
        )

    @classmethod
    def start_pipeline(cls, pipeline_id: str):
        from apps.atomflow.dubbing.models import DubbingAtomPipeline

        try:
            pipeline = DubbingAtomPipeline.objects.select_related("rule").get(id=pipeline_id)

            # 1. 更新状态
            pipeline.status = DubbingAtomPipeline.Status.RUNNING
            pipeline.error_log = ""
            pipeline.save(update_fields=["status", "error_log"])

            logger.info(f"[DubbingScheduler] Starting pipeline {pipeline.name} ({pipeline.id})...")

            # 2. 解析规则，寻找入口 (无依赖的节点)
            rules_config = pipeline.rule.rules_config or []
            start_steps = []

            for step in rules_config:
                deps = step.get("dependence", [])
                if not deps:
                    start_steps.append(step)

            if not start_steps:
                logger.warning(f"[DubbingScheduler] No start steps found for pipeline {pipeline.id}")
                return

            # 3. 点火派发
            for step in start_steps:
                cls.dispatch(str(pipeline.id), step)

        except Exception as e:
            logger.error(f"[DubbingScheduler] Failed to start pipeline {pipeline_id}: {e}", exc_info=True)
            raise e

    @classmethod
    def record_and_dispatch(cls, pipe_ctx, current_seq, mode, slug=None, **kwargs):
        """
        [Override] 重写基类方法，适配 DubbingPipelineContext 的 pipeline_id 属性
        """
        # 1. 记录当前步骤成功 (注意：必须传递 slug 参数)
        pipe_ctx.transit_state(current_seq, slug, "SUCCESS", **kwargs)

        # 2. 模式判定：只有 PROD 模式才会自动寻找并触发下一跳
        if mode == "PROD":
            next_steps = cls.get_next_runnable_steps(
                history=pipe_ctx.get_history(), rules_config=pipe_ctx.get_rules_config(), mode=mode
            )

            for step in next_steps:
                # [Fix] 这里显式使用 pipe_ctx.pipeline_id，解决 AttributeError
                cls.dispatch(pipe_ctx.pipeline_id, step)
