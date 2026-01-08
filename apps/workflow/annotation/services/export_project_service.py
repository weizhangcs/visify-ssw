# apps/workflow/annotation/services/export_project_service.py

import logging
from datetime import datetime

from django.core.files.base import ContentFile

from apps.common.schemas.annotation.workbench import ProjectAnnotation

from .annotation_service import AnnotationService

logger = logging.getLogger(__name__)


class ProjectExportService:
    @staticmethod
    def export_project_package(project) -> ContentFile:
        """
        [项目导出]
        将整个项目的标注数据聚合导出为标准 JSON 文件。
        """
        try:
            # 1. 组装 ProjectAnnotation Schema
            # 获取所有有效的 Job
            valid_jobs = project._get_valid_jobs()  # 假设 Model 保留了基础的 QuerySet 封装

            annotations_map = {}
            character_set = set()

            for job in valid_jobs:
                # 复用 Service 的加载逻辑，确保数据一致性 (含冷/热启动逻辑)
                media_anno = AnnotationService.load_annotation(job)

                # 收集角色
                if media_anno.character_list:
                    character_set.update(media_anno.character_list)

                # 存入 Map
                annotations_map[media_anno.media_id] = media_anno

            project_anno = ProjectAnnotation(
                project_id=str(project.id),
                project_name=project.name,
                character_list=sorted(list(character_set)),
                annotations=annotations_map,
            )

            # 2. 生成文件内容
            file_content = project_anno.model_dump_json(indent=2)

            # 3. 调用 Model 的存储能力 (A/B 轮转)
            project.save_artifact("EXPORT", file_content)

            # 返回 ContentFile 供 View 下载使用
            file_name = f"{project.name}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            return ContentFile(file_content.encode("utf-8"), name=file_name)

        except Exception as e:
            logger.error(f"Export failed for Project {project.id}: {e}", exc_info=True)
            raise e
