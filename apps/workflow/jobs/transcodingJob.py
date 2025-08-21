
from django.db import models
from model_utils import Choices
from django_fsm import FSMField, transition
from ..models import BaseJob
from apps.media_assets.models import Asset

class TranscodingJob(BaseJob):
    PROFILE = Choices(
        ('MP4_720P', 'MP4 720p H.264'),
        ('MP4_1080P', 'MP4 1080p H.264'),
        ('WEBM_VP9', 'WebM VP9'),
    )

    # 关联到具体的媒资，related_name 让我们能方便地从一个 VideoAsset 对象
    # 通过 .jobs 属性反向查询其所有的转码任务。
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE, # 如果源视频被删除，关联的转码任务也一并删除
        related_name='jobs',
        verbose_name="关联媒资"
    )

    # 状态字段现在就是一个普通的 CharField
    status = FSMField(
        max_length=20,
        choices=BaseJob.STATUS,
        default=BaseJob.STATUS.QUEUED,
        verbose_name="任务状态",
        protected=True # 根据文档，可以防止直接修改状态字段
    )

    target_profile = models.CharField(
        max_length=20,
        choices=PROFILE,
        verbose_name="目标规格"
    )

    @transition(field=status, source=BaseJob.STATUS.QUEUED, target=BaseJob.STATUS.PROCESSING)
    def start(self):
        """
        将任务状态从“排队中”转换为“处理中”，并触发后台任务。
        """
        # 2. 在这个状态转换方法内部，调用 Celery 任务
        #transcode_video_task.delay(self.id)

    def __str__(self):
        # self.get_status_display() 是 Django 提供的便捷方法，用于显示 choices 的可读名称
        return f"{self.asset.title} - {self.get_target_profile_display()} ({self.get_status_display()})"

    class Meta:
        verbose_name = "转码任务"
        verbose_name_plural = verbose_name