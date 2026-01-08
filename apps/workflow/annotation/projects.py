# 文件路径: apps/workflow/annotation/projects.py

import logging

from django.core.files.base import ContentFile
from django.db import models
from django.utils.translation import gettext_lazy as _

from ..common.baseProject import BaseProject

logger = logging.getLogger(__name__)


# --- 动态路径辅助函数 ---


def get_audit_upload_path(instance, filename):
    return f"annotation/{instance.id}/audits/{filename}"


def get_project_export_path(instance, filename):
    return f"annotation/{instance.id}/exports/{filename}"


def get_blueprint_upload_path(instance, filename):
    return f"annotation/{instance.id}/blueprints/{filename}"


class AnnotationProject(BaseProject):
    """
    (V5.2 A/B 双缓冲版)
    标注工作流的核心项目模型。
    新增 Current/Backup 版本管理机制，确保产出物的一致性与可回溯性。
    """

    STATUS_CHOICES = (
        ("PENDING", "待处理"),
        ("PROCESSING", "处理中"),
        ("COMPLETED", "已完成"),
        ("FAILED", "失败"),
    )

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="PENDING", verbose_name="项目状态")

    # --- 配置 ---
    source_encoding_profile = models.ForeignKey(
        "configuration.EncodingProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,  # [Legacy Fix] 允许为空，不再强制要求
        verbose_name="源编码配置",
        help_text="选择一个编码配置。标注工具将使用此配置转码后的视频，以加快加载速度。",
    )

    # =========================================================================
    # 三大核心生成物 (Artifacts) - [核心升级: A/B 版本控制]
    # =========================================================================

    # 1. 审计报告 (Data Governance)
    annotation_audit_report = models.FileField(
        upload_to=get_audit_upload_path, blank=True, null=True, verbose_name="标注审计报告 (Current)"
    )
    annotation_audit_report_backup = models.FileField(
        upload_to=get_audit_upload_path, blank=True, null=True, verbose_name="标注审计报告 (Backup)"
    )

    # 2. 工程导出 (Engineering Artifact)
    project_export_file = models.FileField(
        upload_to=get_project_export_path, blank=True, null=True, verbose_name="工程全量导出 (Current)"
    )
    project_export_file_backup = models.FileField(
        upload_to=get_project_export_path, blank=True, null=True, verbose_name="工程全量导出 (Backup)"
    )

    # 3. 生产交付 (Production Artifact)
    final_blueprint_file = models.FileField(
        upload_to=get_blueprint_upload_path, blank=True, null=True, verbose_name="生产消费蓝图 (Current)"
    )
    final_blueprint_file_backup = models.FileField(
        upload_to=get_blueprint_upload_path, blank=True, null=True, verbose_name="生产消费蓝图 (Backup)"
    )

    # [新增] 编排图谱存储
    # 这是连接 "物理审订" 与 "逻辑叙事" 的中间态数据
    orchestration_graph = models.JSONField(
        blank=True, null=True, verbose_name=_("编排图谱 (Orchestration Graph)"), help_text=_("存储用户在编排工作台保存的逻辑结构数据。")
    )

    # =========================================================================
    # 核心业务逻辑
    # =========================================================================

    def _get_valid_jobs(self):
        """辅助方法：获取当前项目下所有有效的标注任务"""
        return (
            # [Refinery适配] 返回所有关联了 Media 的任务。
            # 即使 job.data 为空（冷启动状态），AnnotationService 也能从 Material 读取数据，因此它们也是有效的审计/导出对象。
            self.jobs.select_related("media").order_by("media__sequence_number")
        )

    def save_artifact(self, artifact_type: str, content_str: str):
        """
        [基础设施] 保存产出物 (支持 A/B 轮转)
        Service 层计算好内容后，调用此方法进行持久化存储。
        """
        # 配置映射: Type -> (FilePrefix, CurrentField, BackupField)
        config = {
            "EXPORT": ("project_export", "project_export_file", "project_export_file_backup"),
            "BLUEPRINT": ("blueprint", "final_blueprint_file", "final_blueprint_file_backup"),
            "AUDIT": ("audit_report", "annotation_audit_report", "annotation_audit_report_backup"),
        }

        if artifact_type not in config:
            raise ValueError(f"Unknown artifact type: {artifact_type}")

        file_prefix, current_field_name, backup_field_name = config[artifact_type]

        current_field = getattr(self, current_field_name)
        backup_field = getattr(self, backup_field_name)

        # --- 步骤 1: 备份 (Current -> Backup) ---
        if current_field:
            try:
                # 必须以二进制读取，防止编码问题
                current_field.open("rb")
                existing_content = current_field.read()
                current_field.close()

                if existing_content:
                    backup_filename = f"{file_prefix}_{self.id}_backup.json"
                    backup_field.save(backup_filename, ContentFile(existing_content), save=False)
            except Exception as e:
                # 备份失败不应阻断主流程（比如文件被手动删除了），记录警告即可
                logger.warning(f"Project {self.id}: Failed to rotate backup for {file_prefix}: {e}")

        # --- 步骤 2: 写入新文件 (New -> Current) ---
        new_filename = f"{file_prefix}_{self.id}.json"

        getattr(self, current_field_name).save(
            new_filename,
            ContentFile(content_str.encode("utf-8")),
            save=True,  # 这里触发最终的 DB 落盘，将 Current 和 Backup 的路径变更一并保存
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "标注项目"
        verbose_name_plural = "标注项目"
