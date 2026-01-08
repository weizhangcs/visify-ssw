# apps/workflow/annotation/services/import_project_service.py

import json
import logging

from django.db import transaction

from apps.media_assets.models import Asset

from ..jobs import AnnotationJob
from ..projects import AnnotationProject
from ..services.annotation_service import AnnotationService
from ..services.audit_service import ArtifactAuditService

logger = logging.getLogger(__name__)


class ProjectImportService:
    @classmethod
    @transaction.atomic
    def execute_import(cls, json_file, target_asset_id, project_name_override=None):
        try:
            # 1. 加载数据
            data = json.load(json_file)
            target_asset = Asset.objects.get(id=target_asset_id)

            imported_annotations = data.get("annotations", {})
            # 获取目标 Asset 的所有 Media，建立 Sequence 索引映射，以便 O(1) 查找
            # Map: { 1: MediaObject, 2: MediaObject }
            target_media_map = {m.sequence_number: m for m in target_asset.medias.all()}
            # 同时保留列表用于降级处理
            target_medias_list = list(target_asset.medias.order_by("sequence_number"))

            if not target_media_map:
                raise ValueError(f"目标资产 '{target_asset.title}' 下没有媒体文件，无法导入。")

            # 2. 创建新项目
            new_project = AnnotationProject.objects.create(
                name=project_name_override or f"{data.get('project_name', 'Imported')} (恢复)",
                asset=target_asset,
                status="PROCESSING",
                description=f"从文件导入。原项目ID: {data.get('project_id')}",
            )

            # 3. 核心：基于 Sequence 的智能匹配
            # 假设 imported_annotations 是 dict (key=old_media_id) 或 list
            import_items = (
                list(imported_annotations.values()) if isinstance(imported_annotations, dict) else imported_annotations
            )

            for i, item_data in enumerate(import_items):
                # --- [架构协同修正点] ---
                # 优先尝试读取 sequence_number 进行精准匹配
                seq_num = item_data.get("sequence_number")
                target_media = None

                if seq_num is not None and seq_num in target_media_map:
                    # Case A: 精准命中 (最佳情况)
                    target_media = target_media_map[seq_num]
                elif i < len(target_medias_list):
                    # Case B: 数据包是旧版本(无seq) 或 序号不匹配，回退到索引对齐
                    target_media = target_medias_list[i]
                    if seq_num is not None:
                        logger.warning(f"导入警告: 序号 {seq_num} 未在目标资产中找到，已回退到按位置索引匹配 Media: {target_media.title}")
                else:
                    logger.warning(f"导入跳过: 无法找到匹配的 Media (Index: {i}, Seq: {seq_num})")
                    continue

                # 4. 数据清洗与 ID 替换 (保持原有逻辑，但基于确认的 target_media)
                item_data["media_id"] = str(target_media.id)
                item_data["file_name"] = target_media.title
                item_data["source_path"] = target_media.source_video.name if target_media.source_video else ""
                item_data["duration"] = target_media.duration or item_data.get("duration", 0)
                # 确保 sequence_number 在新项目中也是正确的 (即使是 Case B 回退的情况)
                item_data["sequence_number"] = target_media.sequence_number

                # [Optimization] 如果导入数据中包含 waveform_data (旧版本导出)，将其移除
                # 强制使用当前环境 Material 的波形数据
                item_data.pop("waveform_data", None)

                # 创建 Job
                job = AnnotationJob.objects.create(project=new_project, media=target_media, status="COMPLETED")

                # 保存标注数据
                AnnotationService.save_annotation(job, item_data)

            # 5. 收尾
            # [Refactor] 调用 AuditService 而不是 AnnotationService
            ArtifactAuditService.run_project_audit(new_project)
            return new_project

        except Exception as e:
            logger.error(f"导入项目失败: {e}", exc_info=True)
            raise ValueError(f"导入过程中发生错误，已回滚: {str(e)}")
