# 文件路径: apps/workflow/annotation/jobs.py

import logging

from django.core.files.storage import FileSystemStorage
from django.db import models
from django_fsm import transition

from apps.media_assets.models import Media

from ..common.baseJob import BaseJob

logger = logging.getLogger(__name__)

# =============================================================================
# [Deprecated] 仅保留以兼容旧迁移文件引用 (如 0002_...)。
# 新业务逻辑已迁移至 JSONField，请勿在新代码中使用以下对象。
# =============================================================================
fs = FileSystemStorage(location="/app/media_root")


def get_annotation_upload_path(instance, filename):
    return f"annotation/{instance.project.id}/jobs/{instance.id}_{filename}"


# =============================================================================


class AnnotationJob(BaseJob):
    """
    (V5.2 A/B 双缓冲版)
    标注工作流的“原子任务”模型。
    新增 Current/Backup 版本管理机制。
    """

    # --- 关联关系 ---
    project = models.ForeignKey(
        "AnnotationProject", on_delete=models.CASCADE, related_name="jobs", verbose_name="所属标注项目"
    )

    media = models.ForeignKey(Media, on_delete=models.CASCADE, related_name="annotation_jobs", verbose_name="关联媒体文件")

    # --- 核心产出物 (SSOT) ---

    # 1. Current (当前工作版本)
    # [变更] 改为 JSONField (PostgreSQL jsonb)，不再使用文件存储
    data = models.JSONField(default=dict, blank=True, verbose_name="标注数据 (Current)", help_text="当前工作区的全量标注数据")

    # 2. Backup (上一版本/修订前快照)
    data_backup = models.JSONField(default=dict, blank=True, verbose_name="标注数据 (Backup)", help_text="上一次保存或修订前的快照")

    # --- 基础设施: A/B 轮转逻辑 ---

    def rotate_and_save(self, new_data: dict, save_to_db: bool = True):
        """
        [Job级 A/B 轮转]
        当保存新的标注数据时调用：
        1. Current -> Backup
        2. New -> Current
        """
        # 1. 备份 Current -> Backup (内存操作)
        if self.data:
            self.data_backup = self.data

        # 2. 写入 New -> Current
        self.data = new_data

        # 3. 落盘
        if save_to_db:
            self.save(update_fields=["data", "data_backup", "modified"])

    def rollback_to_backup(self):
        """
        [回滚能力]
        当用户点击“放弃修订”或“回退”时调用。
        将 Backup 覆盖回 Current。
        """
        if not self.data_backup:
            return False, "No backup available."

        try:
            # 覆盖 Current
            self.data = self.data_backup
            self.save(update_fields=["data", "modified"])
            return True, "Rollback successful."
        except Exception as e:
            return False, str(e)

    # --- 状态机转换 ---

    @transition(field="status", source=BaseJob.STATUS.PENDING, target=BaseJob.STATUS.PROCESSING)
    def start_annotation(self):
        """开始标注"""
        pass

    @transition(
        field="status",
        source=[
            BaseJob.STATUS.PENDING,  # [Fix] 允许未开始的任务直接被项目审计批量完成
            BaseJob.STATUS.PROCESSING,
            BaseJob.STATUS.REVISING,
            BaseJob.STATUS.ERROR,
        ],
        target=BaseJob.STATUS.COMPLETED,
    )
    def complete_annotation(self):
        """完成标注"""
        pass

    @transition(field="status", source=BaseJob.STATUS.COMPLETED, target=BaseJob.STATUS.REVISING)
    def revise(self):
        """
        [修订逻辑增强]
        当任务从 COMPLETED 变为 REVISING 时，强制执行一次备份。
        这样如果修订改乱了，用户可以用 rollback_to_backup 恢复到 COMPLETED 时的状态。
        """
        # 显式触发一次“原地轮转”：把 Current 复制给 Backup，Current 保持不变
        if self.data:
            self.data_backup = self.data
            # 这里不立即 save，因为状态转换通常会在 View 层调 save()
            # 但为了保险起见，如果 django-fsm 不自动保存字段，可能需要手动处理

        # 状态变更交给 django-fsm
        super().revise()

    def __str__(self):
        return f"Job {self.id} | {self.media.title} ({self.get_status_display()})"

    class Meta:
        verbose_name = "标注任务"
        verbose_name_plural = verbose_name
        ordering = ["media__sequence_number", "id"]
