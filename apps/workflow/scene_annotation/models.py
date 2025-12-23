# apps/workflow/scene_annotation/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField
from model_utils import Choices

from ..common.baseJob import BaseJob

# 严格对齐 Transcoding 范式：引入基类
from ..common.baseProject import BaseProject


class SceneAnnotationProject(BaseProject):
    """
    场景标注项目 (Asset 级别)
    范式：继承 BaseProject，使用外键关联 Asset，引入 FSMField 状态机
    """

    STATUS = Choices(("PENDING", _("等待开始")), ("PROCESSING", _("处理中")), ("COMPLETED", _("已完成")), ("FAILED", _("失败")))

    # 对齐 TranscodingProject：外键关联 Asset
    asset = models.ForeignKey(
        "media_assets.Asset", on_delete=models.CASCADE, related_name="scene_annotation_projects", verbose_name=_("关联资产")
    )

    name = models.CharField(max_length=255, verbose_name=_("项目名称"))
    description = models.TextField(blank=True, null=True, verbose_name=_("项目描述"))

    # 对齐 TranscodingProject：使用 FSMField 管理状态
    status = FSMField(
        default=STATUS.PENDING,
        verbose_name=_("项目状态"),
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("场景标注项目")
        verbose_name_plural = _("场景标注项目")


class SceneAnnotationJob(BaseJob):
    """
    场景标注执行任务 (Media/Execution 级别)
    范式：继承 BaseJob，关联具体的物理媒资
    """

    project = models.ForeignKey(
        SceneAnnotationProject, on_delete=models.CASCADE, related_name="scene_annotation_jobs", verbose_name=_("所属场景项目")
    )

    media = models.ForeignKey(
        "media_assets.Media", on_delete=models.CASCADE, related_name="scene_annotation_jobs", verbose_name=_("关联媒体文件")
    )

    cloud_task_id = models.CharField(max_length=64, blank=True, null=True, db_index=True, verbose_name=_("云端任务ID"))
    result = models.JSONField(verbose_name=_("结果数据"), blank=True, null=True)

    class Meta:
        verbose_name = _("场景标注任务日志")
        verbose_name_plural = _("场景标注任务日志")
        ordering = ["-created"]
