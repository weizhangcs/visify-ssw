# apps/workflow/creative/models.py

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.workflow.common.baseProject import BaseProject

# from apps.workflow.inference.projects import InferenceProject


class CreativeProject(BaseProject):
    """
    [重构] 创作项目：单管道精细化生产的核心容器。
    """

    class Status(models.TextChoices):
        CREATED = "CREATED", _("Created")
        # Step 1
        NARRATION_RUNNING = "NARRATION_RUNNING", _("Generating Narration")
        NARRATION_COMPLETED = "NARRATION_COMPLETED", _("Narration Ready")
        # Step 1.5
        LOCALIZATION_RUNNING = "LOCALIZATION_RUNNING", _("Localizing")
        LOCALIZATION_COMPLETED = "LOCALIZATION_COMPLETED", _("Localized")
        # Step 2
        AUDIO_RUNNING = "AUDIO_RUNNING", _("Generating Audio")
        AUDIO_COMPLETED = "AUDIO_COMPLETED", _("Audio Ready")
        # Step 3
        EDIT_RUNNING = "EDIT_RUNNING", _("Generating EditingScript")
        EDIT_COMPLETED = "EDIT_COMPLETED", _("EditingScript Ready")
        # Step 4
        SYNTHESIS_RUNNING = "SYNTHESIS_RUNNING", _("Synthesizing")

        COMPLETED = "COMPLETED", _("All Done")
        FAILED = "FAILED", _("Failed")

    # [新增] 项目类型定义
    class Type(models.TextChoices):
        DEFAULT = "default", _("标准创作 (Director)")
        TEMPLATE = "template", _("母本模板 (Template)")
        BATCH = "batch", _("批量衍生 (Batch)")

    # --- 字段定义 ---

    # inference_project = models.ForeignKey(
    # InferenceProject, on_delete=models.CASCADE, related_name="creative_projects", verbose_name=_("关联推理项目")
    # )

    # [新增] 类型字段
    project_type = models.CharField(max_length=20, choices=Type.choices, default=Type.DEFAULT, verbose_name=_("项目类型"))

    # [移除] batch 字段 (已废弃)

    # --- 产出物文件 (Assets) ---

    # Step 1: Narration
    narration_script_file = models.FileField(
        upload_to="creative/narration/", null=True, blank=True, verbose_name=_("解说词脚本 (JSON)")
    )

    # Step 1.5: Localization
    localized_script_file = models.FileField(
        upload_to="creative/localized/", null=True, blank=True, verbose_name=_("本地化脚本 (JSON)")
    )

    # Step 2: Audio
    dubbing_script_file = models.FileField(
        upload_to="creative/dubbing/", null=True, blank=True, verbose_name=_("配音脚本 (JSON)")
    )

    # Step 3: Edit
    edit_script_file = models.FileField(
        upload_to="creative/edit/", null=True, blank=True, verbose_name=_("剪辑脚本 (JSON)")
    )

    # Step 4: Synthesis
    final_video_file = models.FileField(upload_to="creative/output/", null=True, blank=True, verbose_name=_("最终成片"))

    # 配置快照
    auto_config = models.JSONField(default=dict, blank=True, verbose_name=_("参数配置快照"))

    status = models.CharField(max_length=50, choices=Status.choices, default=Status.CREATED, verbose_name=_("当前状态"))

    class Meta:
        verbose_name = _("创作项目 (Creative Project)")
        verbose_name_plural = _("创作项目 (Creative Projects)")
        ordering = ["-modified"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
