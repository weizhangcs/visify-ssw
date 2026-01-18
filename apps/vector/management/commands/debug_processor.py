import json
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.vector.services.processor import DataProcessorService
from apps.workflow.annotation.jobs import AnnotationJob

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "白盒验证 Processor 对真实业务数据的处理效果 (读取开发库数据)"

    def add_arguments(self, parser):
        parser.add_argument("target_id", type=str, help="AnnotationJob ID (Int) 或 Material ID (UUID)")

    def handle(self, *args, **options):
        target_id = options["target_id"]
        self.stdout.write(f"Looking up job for ID: {target_id}...")

        job = self._find_job(target_id)
        if not job:
            self.stdout.write(self.style.ERROR(f"Could not find AnnotationJob for ID: {target_id}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Found Job: {job} (ID: {job.id})"))

        # 定义输出目录
        output_dir = Path(settings.BASE_DIR) / "tests" / "testdata" / "vector"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 提取真实数据
        data_map = {"frame": job.frames, "scene": job.scenes, "dialogue": job.dialogues, "slice": job.slices}

        for index_type, data_list in data_map.items():
            if not data_list:
                self.stdout.write(f"  - {index_type}: No data found.")  # noqa: E221
                continue

            self.stdout.write(f"  - {index_type}: Processing {len(data_list)} items...")  # noqa: E221
            self._process_list_and_save(index_type, data_list, str(job.id), target_id, output_dir)

        self.stdout.write(self.style.SUCCESS(f"All outputs saved to: {output_dir}"))

    def _find_job(self, target_id):
        # 1. 尝试作为 AnnotationJob ID (Int)
        try:
            # 尝试转为 int，如果成功则查询
            job_id = int(target_id)
            return AnnotationJob.objects.get(id=job_id)
        except (ValueError, AnnotationJob.DoesNotExist):
            pass

        # 2. 尝试作为 Material ID (UUID)
        try:
            # 动态导入以防 atomflow 未安装
            from apps.atomflow.models import Material

            material = Material.objects.get(id=target_id)
            return AnnotationJob.objects.filter(media=material.media).first()
        except (ImportError, Exception):
            pass

        return None

    def _process_list_and_save(self, index_type, data_list, job_id, target_input_id, output_dir):
        results = []
        for item in data_list:
            processed_text = DataProcessorService.extract_text(item, index_type)
            results.append({"item_id": item.get("id"), "processed_text": processed_text, "source_data": item})

        output_content = {
            "meta": {
                "job_id": job_id,
                "target_input_id": target_input_id,
                "index_type": index_type,
                "processor": "DataProcessorService",
                "count": len(results),
            },
            "results": results,
        }

        filename = f"{index_type}_{job_id}_debug.json"
        file_path = output_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(output_content, f, ensure_ascii=False, indent=2)

        self.stdout.write(f"  -> Generated {filename}")  # noqa: E221
