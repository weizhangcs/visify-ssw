from apps.common.atomflow.base_contexts import BasePipelineContext

from ..models import RefineryAtomPipeline


class RefineryPipelineContext(BasePipelineContext):
    """
    [修正] 真实的执行上下文：
    通过 get_pipeline_instance 获取数据库中的轨迹记录。
    """

    def get_pipeline_instance(self):
        # [Fix] 预加载 rule 以优化查询，并注入缺失的 mode 属性
        pipeline = RefineryAtomPipeline.objects.select_related("rule").get(id=self.pipeline_id)
        if not hasattr(pipeline, "mode"):
            pipeline.mode = pipeline.rule.mode
        return pipeline
