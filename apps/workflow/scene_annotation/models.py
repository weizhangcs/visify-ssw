from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


class SceneAnnotationProject(TimeStampedModel):
    """
    场景标注项目 (Asset 级别)
    通常一个 Asset 对应一个 Project，管理其下所有的 Job
    """

    asset_id = models.UUIDField(verbose_name=_("Asset ID"), db_index=True)
    # 冗余字段方便查询
    title = models.CharField(max_length=255, verbose_name=_("Project Title"), blank=True)

    class Meta:
        verbose_name = _("Scene Annotation Project")
        verbose_name_plural = _("Scene Annotation Projects")

    def __str__(self):
        return f"{self.title} ({self.asset_id})"


class SceneAnnotationJob(TimeStampedModel):
    """
    场景标注执行任务 (Media/Execution 级别)
    记录每次运行的状态、Cloud Task ID 以及最终结果
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        PROCESSING = "PROCESSING", _("Processing (Slicing/Uploading)")
        CLOUD_SUBMITTED = "CLOUD_SUBMITTED", _("Submitted to Cloud")
        COMPLETED = "COMPLETED", _("Completed")
        FAILED = "FAILED", _("Failed")

    project = models.ForeignKey(SceneAnnotationProject, on_delete=models.CASCADE, related_name="jobs")

    # 关联具体的物理媒资
    media_id = models.UUIDField(verbose_name=_("Media ID"), db_index=True)

    # Cloud 侧返回的任务 ID，用于轮询
    cloud_task_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)

    # 存储最终结果 (Cloud 返回的 Scenes)
    result = models.JSONField(verbose_name=_("Result Data"), blank=True, null=True)

    # 错误信息
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = _("Scene Annotation Job")

    def __str__(self):
        return f"Job {self.id} - {self.get_status_display()}"
