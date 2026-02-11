from apps.atomflow.dubbing.models import DubbingAtomPipeline
from apps.common.atomflow.base_contexts import BasePipelineContext


class DubbingPipelineContext(BasePipelineContext):
    """
    Dubbing 流程上下文
    """

    def get_pipeline_instance(self):
        pipeline = DubbingAtomPipeline.objects.select_related("rule").get(id=self.pipeline_id)
        if not hasattr(pipeline, "mode"):
            pipeline.mode = pipeline.rule.mode
        return pipeline
