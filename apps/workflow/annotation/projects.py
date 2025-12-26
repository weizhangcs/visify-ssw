# 文件路径: apps/workflow/annotation/projects.py

import json
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
        blank=False,
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
            self.jobs.filter(annotation_file__isnull=False)
            .exclude(annotation_file="")
            .select_related("media")
            .order_by("media__sequence_number")
        )

    def _rotate_and_save(self, content_str: str, file_prefix: str, current_field_name: str, backup_field_name: str):
        """
        [基础设施: A/B 轮转保存]
        1. 检查 Current 是否存在。
        2. 如果存在，将其内容搬运到 Backup。
        3. 将新内容写入 Current。

        TODO: 基于此结构开发 rollback() 方法，允许将 backup_field 的内容覆盖回 current_field。
        """
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
                    # save=False: 我们不希望在这里触发数据库 UPDATE，只写文件
                    # 注意：FileField.save 默认行为取决于 Storage Backend，
                    # 通常 save=False 只会更新内存里的 Model 实例，不会立即 commit 到 DB，
                    # 只有最后的 save() 才会把两个字段的路径更新一起提交。

                    # [Fix] 直接使用 backup_field 变量，修复 unused variable 警告
                    backup_field.save(backup_filename, ContentFile(existing_content), save=False)
            except Exception as e:
                # 备份失败不应阻断主流程（比如文件被手动删除了），记录警告即可
                logger.warning(f"Project {self.id}: Failed to rotate backup for {file_prefix}: {e}")

        # --- 步骤 2: 写入新文件 (New -> Current) ---
        new_filename = f"{file_prefix}_{self.id}.json"

        # 这里虽然也可以用 current_field 变量，但为了确保 save 行为作用于 self 实例的最新状态，
        # 保持 getattr 也是可以的，不过为了风格统一，既然上面获取了对象，这里也可以直接用：
        # current_field.save(...)
        # 但考虑到 FileField 的 save 方法有时会有副作用，最稳妥的方式还是通过 getattr 确保拿到的是绑定的 FieldFile
        getattr(self, current_field_name).save(
            new_filename,
            ContentFile(content_str.encode("utf-8")),
            save=True,  # 这里触发最终的 DB 落盘，将 Current 和 Backup 的路径变更一并保存
        )

    def export_project_annotation(self):
        """
        [聚合逻辑] 读取所有 Job 的 JSON -> 完整保留 Context -> 合并
        """
        from .schemas import ProjectAnnotation
        from .services.annotation_service import AnnotationService

        project_anno = ProjectAnnotation(
            project_id=str(self.id), project_name=self.name, character_list=[], annotations={}
        )

        valid_jobs = self._get_valid_jobs()
        for job in valid_jobs:
            try:
                # 获取全量数据
                media_anno = AnnotationService.load_annotation(job)
                project_anno.annotations[media_anno.media_id] = media_anno
            except Exception as e:
                logger.error(f"Project Export Error on Job {job.id}: {e}")

        json_output = project_anno.model_dump_json(indent=2)

        # [修改] 使用 A/B 轮转
        self._rotate_and_save(
            content_str=json_output,
            file_prefix="project_export",
            current_field_name="project_export_file",
            backup_field_name="project_export_file_backup",
        )

        return project_anno

    def generate_blueprint(self):
        """
        [聚合逻辑] 读取所有 Job 的 JSON -> 清洗 -> 合并
        """
        from .schemas import Blueprint, Chapter
        from .services.annotation_service import AnnotationService

        blueprint = Blueprint(
            project_id=str(self.id),
            asset_id=str(self.asset.id) if self.asset else "",
            project_name=self.name,
            global_character_list=[],
            chapters={},
        )

        all_characters = set()
        valid_jobs = self._get_valid_jobs()

        for job in valid_jobs:
            try:
                media_anno = AnnotationService.load_annotation(job)
                # 清洗数据
                clean_data = media_anno.get_clean_business_data()

                # 转换为 Chapter
                chapter = Chapter(
                    id=str(media_anno.media_id),
                    name=media_anno.file_name,
                    source_file=media_anno.source_path,
                    duration=media_anno.duration,
                    sequence_number=media_anno.sequence_number,
                    **clean_data,
                )

                blueprint.chapters[chapter.id] = chapter

                # 收集角色
                for d in clean_data.get("dialogues", []):
                    spk = d.get("speaker")
                    if spk and spk != "Unknown":
                        all_characters.add(spk)

            except Exception as e:
                logger.error(f"Blueprint Aggregation Error on Job {job.id}: {e}")
                continue

        blueprint.global_character_list = sorted(list(all_characters))

        json_output = blueprint.model_dump_json(indent=2, exclude_none=True)

        # [修改] 使用 A/B 轮转
        self._rotate_and_save(
            content_str=json_output,
            file_prefix="blueprint",
            current_field_name="final_blueprint_file",
            backup_field_name="final_blueprint_file_backup",
        )

        return blueprint

    def run_audit(self):
        """
        [能力 3: 生成审计报告 + 强制同步生成蓝图]
        这是一个复合原子操作：
        1. 重新生成 Blueprint (确保发给 Cloud 的是最新数据)
        2. 执行 Audit (确保 UI 看到的是最新数据)
        """

        from .services.audit_service import ArtifactAuditService

        # 1. [关键] 强制刷新蓝图
        # 即使 blueprint 没变，重新生成一次的成本远低于数据不一致的风险
        self.generate_blueprint()

        # 2. 执行审计 (Service 会重新读取 Jobs，这和 generate_blueprint 读的是同一份数据源)
        report_data = ArtifactAuditService.audit_project(self)

        json_output = json.dumps(report_data, indent=2, ensure_ascii=False)

        # [修改] 使用 A/B 轮转
        self._rotate_and_save(
            content_str=json_output,
            file_prefix="audit_report",
            current_field_name="annotation_audit_report",
            backup_field_name="annotation_audit_report_backup",
        )

        return report_data

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "标注项目"
        verbose_name_plural = "标注项目"
