import logging

from apps.common.atomflow.base_contexts import BasePipelineContext

from ..models import RefineryAtomPipeline

logger = logging.getLogger(__name__)


class RefineryPipelineContext(BasePipelineContext):
    """
    [流程上下文] Refinery 专用 Pipeline 上下文。

    职责：
    1. 管理 RefineryAtomPipeline 的生命周期。
    2. 隔离调度引擎与数据库，提供统一的状态流转接口。
    3. 注入必要的运行时属性（如 mode）。
    """

    def __init__(self, pipeline_id):
        super().__init__(pipeline_id)
        self._pipeline_instance = None

    @property
    def pipeline(self):
        if self._pipeline_instance is None:
            self._pipeline_instance = self.get_pipeline_instance()
        return self._pipeline_instance

    def get_pipeline_instance(self):
        """
        [Internal] 从数据库加载 Pipeline 模型实例。
        预加载 rule 以优化查询，并注入缺失的 mode 属性。
        """
        pipeline = RefineryAtomPipeline.objects.select_related("rule").get(id=self.pipeline_id)
        if not hasattr(pipeline, "mode"):
            pipeline.mode = pipeline.rule.mode
        return pipeline
