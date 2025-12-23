# 文件路径: apps/workflow/character_annotation/models.py

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.media_assets.models import Media

# 严格继承存量基类
from apps.workflow.common.baseJob import BaseJob
from apps.workflow.common.baseProject import BaseProject


class CharacterAnnotationProject(BaseProject):
    """
    (V1.2 - 显式 ID 强化版)
    角色预标注项目容器。
    继承 BaseProject，
    自动获得: id (UUID), asset, name, description, status, created, modified。
    """

    # 扩展字段
    override_characters = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("覆盖角色列表"),
        help_text=_("JSON 格式的角色名称列表。若为空，则默认使用关联 Asset 的 known_characters。"),
    )

    class Meta:
        verbose_name = _("角色标注项目")
        verbose_name_plural = _("角色标注项目")
        ordering = ["-created"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class CharacterAnnotationJob(BaseJob):
    """
    (V1.2 - 显式 ID 强化版)
    角色预标注原子任务。
    继承 BaseJob，
    自动获得 FSM 状态机 (status) 及 .start(), .complete(), .fail() 方法。
    """

    # [核心修复] 必须显式声明 default=uuid.uuid4，否则 Django 在 create 时可能传 null 给 PostgreSQL
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name="ID")

    project = models.ForeignKey(
        CharacterAnnotationProject, on_delete=models.CASCADE, related_name="jobs", verbose_name=_("所属项目")
    )

    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name="character_jobs", verbose_name=_("关联媒体"))

    # --- 外部系统关联 ---
    cloud_task_id = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("云端任务 ID"))

    # --- 结果产出 ---
    output_ass_file = models.FileField(
        upload_to="character_annotation/outputs/%Y/%m/%d/", blank=True, null=True, verbose_name=_("生成的 ASS 字幕文件")
    )

    character_stats = models.JSONField(default=dict, blank=True, null=True, verbose_name=_("角色统计信息"))

    error_message = models.TextField(blank=True, null=True, verbose_name=_("错误信息"))

    def __str__(self):
        return f"Job: {self.media.title} [{self.get_status_display()}]"

    class Meta:
        verbose_name = _("角色标注任务")
        verbose_name_plural = _("角色标注任务")
        ordering = ["media__sequence_number"]
