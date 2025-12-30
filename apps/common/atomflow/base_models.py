from django.core.exceptions import ValidationError
from django.db import models
from model_utils.models import TimeStampedModel

from .schemas import AtomflowRuleSchema  # 引入强约束


class BaseAtomUnit(TimeStampedModel):
    """
    [能力层] 原子算子能力定义表
    """

    class ExecMode(models.TextChoices):
        SYNC = "SYNC", "同步"
        ASYNC = "ASYNC", "异步"

    class ResourceClass(models.TextChoices):
        GENERAL = "GENERAL", "通用"
        NETWORK = "NETWORK", "网络"
        IO = "IO", "存储"
        COMPUTING = "COMPUTING", "计算"
        AI = "AI", "人工智能"
        TRANSFER = "TRANSFER", "传输"

    name = models.CharField(max_length=100)
    slug = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)

    execution_mode = models.CharField(max_length=10, choices=ExecMode.choices)
    resource_class = models.CharField(max_length=20, choices=ResourceClass.choices)

    # 逻辑判断：由子类实现具体的物理/逻辑判定
    def is_ready(self, target) -> bool:
        """检查前置数据是否已就绪"""
        raise NotImplementedError

    def is_done(self, target) -> bool:
        """检查结果数据是否已生成"""
        raise NotImplementedError

    class Meta:
        abstract = True


class BaseAtomflowRule(TimeStampedModel):
    """
    [逻辑层] 算子编排规则表
    """

    class Mode(models.TextChoices):
        PROD = "PROD", "生产模式"
        DEBUG = "DEBUG", "调试模式"

    name = models.CharField(max_length=100)
    description = models.TextField(null=True, blank=True)
    slug = models.CharField(max_length=50, unique=True)
    mode = models.CharField(max_length=10, default="PROD")

    # 使用 JSONField 存储，但增加保存时的 Schema 校验
    rules_config = models.JSONField(default=list)

    def clean(self):
        """利用 Pydantic 在保存前强制校验 JSON 格式"""
        try:
            AtomflowRuleSchema(rules=self.rules_config)
        except Exception as e:
            raise ValidationError(f"Invalid rules_config Schema: {e}")

    class Meta:
        abstract = True


class BaseAtomPipeline(TimeStampedModel):
    """
    [实例层] 流程执行记录表 (灵魂)
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "等待"
        RUNNING = "RUNNING", "运行中"
        SUCCESS = "SUCCESS", "已完成"
        FAILED = "FAILED", "失败"
        STOPPED = "STOPPED", "已停止"

    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # 运行时数据
    metrics = models.JSONField(default=dict, help_text="记录格式: {seq: {status, duration, at, error}}")
    # 约定 metrics 结构:
    # {
    #   "1": {"status": "SUCCESS", "duration": 0.5, "finished_at": "...", "error": null},
    #   "2": {"status": "FAILED", "duration": 0.1, "finished_at": "...", "error": "Timeout"}
    # }

    stop_point = models.IntegerField(null=True, blank=True, help_text="最后停下的 seq 编号")
    error_log = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True
