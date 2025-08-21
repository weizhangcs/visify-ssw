# jobs/models.py

from model_utils.models import TimeStampedModel
from model_utils import Choices
from django_fsm import FSMField, transition

class BaseJob(TimeStampedModel):
    STATUS = Choices(
        ('QUEUED', '排队中'),
        ('PROCESSING', '处理中'),
        ('COMPLETED', '已完成'),
        ('ERROR', '错误'),
        ('QA_PENDING', '待审核')
    )

    # --- 所有 Job 共有的字段 ---
    status = FSMField(default=STATUS.QUEUED, protected=True, verbose_name="任务状态")
    # 还可以添加如 priority, assigned_to 等通用字段

    # --- 所有 Job 共有的方法 ---
    @transition(field='status', source=STATUS.QUEUED, target=STATUS.PROCESSING)
    def start(self):
        """这个方法将被具体的 Job 类继承。"""
        # 具体的任务派发逻辑可以在子类中实现或在触发它的地方实现
        pass

    @transition(field='status', source=STATUS.PROCESSING, target=STATUS.COMPLETED)
    def complete(self):
        pass

    @transition(field='status', source='*', target=STATUS.ERROR)
    def fail(self):
        pass

    class Meta:
        # 关键！这告诉 Django，不要为这个模型创建数据库表。
        # 它只是一个用来被其他模型继承的“模板”。
        abstract = True