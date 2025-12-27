# apps/refinery/services/text_analyzer.py
import logging

from apps.workflow.annotation.services.srt_parser import parse_srt_content

logger = logging.getLogger(__name__)


class TextAnalyzerService:
    @staticmethod
    def execute_and_report(material_id: str):
        """
        [原子服务] 文本清洗与结构化
        职责：读取原始 SRT，转换为 JSON 存入 Material
        """
        from apps.refinery.models import Material

        material = Material.objects.get(id=material_id)
        source_sub = material.media.source_subtitle

        if not source_sub:
            logger.warning(f"Material {material_id} has no source subtitle, skipping.")
            return

        try:
            # 1. 读取原始文件内容
            with source_sub.open("r") as f:
                content = f.read()
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="ignore")

            # 2. 调用存量解析算法 (复用存量代码中的解析能力)
            # 产出格式: [{'start': 1.0, 'end': 2.0, 'text': '...', 'speaker': '...', 'original_text': '...'}]
            dialogue_list = parse_srt_content(content)

            # 3. 数据落地
            material.dialogue_track = dialogue_list

            # 4. 范式闭环：回归 PENDING
            if material.status == Material.Status.ANALYZING_TEXT:
                material.finish_current_task()

            material.save(update_fields=["dialogue_track", "status", "modified"])
            logger.info(f"Successfully refined dialogue track for Material {material_id}")

        except Exception as e:
            logger.error(f"Text analysis failed for {material_id}: {e}")
            raise
