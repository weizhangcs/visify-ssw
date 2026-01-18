# 文件路径: apps/vector/models.py

from django.db import models
from model_utils.models import TimeStampedModel

from apps.workflow.annotation.jobs import AnnotationJob


class VectorIndex(TimeStampedModel):
    """
    [Production Asset] 向量索引资产表。
    负责管理生产域产出的索引文件，提供版本控制和状态查询。
    """

    # 关联的业务对象 ID (通常是 AnnotationJob ID，但保持松耦合使用 CharField)
    target_id = models.CharField(max_length=64, db_index=True, verbose_name="关联目标ID")

    # 索引类型 (dialogue, scene, slice, frame)
    index_type = models.CharField(max_length=32, verbose_name="索引类型")

    # 物理路径 (相对于 MEDIA_ROOT)
    file_path = models.CharField(max_length=1024, verbose_name="索引文件路径")

    # 资产元数据
    vector_count = models.IntegerField(default=0, verbose_name="向量数量")
    dimension = models.IntegerField(default=0, verbose_name="向量维度")
    model_name = models.CharField(max_length=128, verbose_name="Embedding模型")

    # 状态标记 (用于 A/B 测试或回滚)
    is_active = models.BooleanField(default=True, verbose_name="是否启用")

    class Meta:
        verbose_name = "向量索引资产"
        verbose_name_plural = "向量索引资产"
        # 确保同一目标同一类型只有一个活跃索引 (或者根据业务逻辑调整)
        indexes = [
            models.Index(fields=["target_id", "index_type"]),
        ]

    def __str__(self):
        return f"Index({self.index_type}) for {self.target_id} [{self.vector_count}]"


class VectorSourceJob(AnnotationJob):
    """
    [Proxy Model] 待索引的标注任务。
    用于在 Vector Admin 中直接选择 AnnotationJob 并触发索引构建，而不侵入 Workflow 代码。
    """

    class Meta:
        proxy = True
        verbose_name = "待索引标注任务"
        verbose_name_plural = "待索引标注任务"
