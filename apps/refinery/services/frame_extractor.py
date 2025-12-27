# 文件路径: apps/refinery/services/frame_extractor.py

import concurrent.futures
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


class FrameExtractorService:
    @staticmethod
    def execute_and_report(material_id: str):
        from apps.refinery.models import Material

        with transaction.atomic():
            material = Material.objects.select_for_update().get(id=material_id)

            if not material.visual_slices or not material.proxy_video:
                raise ValueError(f"Extractor Failed: Material {material_id} 缺失切片数据或 Proxy 视频。")

            proxy_abs_path = Path(settings.MEDIA_ROOT) / material.proxy_video
            rel_frames_dir = Path("refinery") / "frames" / str(material_id)
            abs_frames_dir = Path(settings.MEDIA_ROOT) / rel_frames_dir

            if abs_frames_dir.exists():
                shutil.rmtree(abs_frames_dir)
            abs_frames_dir.mkdir(parents=True, exist_ok=True)

            try:
                total_count = len(material.visual_slices)
                logger.info(
                    f"Refinement: Starting massive frame extraction for {material_id}. Total: {total_count} slices."
                )

                # --- 增强：多线程并行提取 + 进度监控 ---
                updated_slices = FrameExtractorService._parallel_extract_with_progress(
                    proxy_abs_path, material.visual_slices, abs_frames_dir, rel_frames_dir
                )

                # 数据回填与范式回归
                material.visual_slices = updated_slices
                if material.status == material.Status.FRAME_EXTRACTING:
                    material.finish_current_task()

                material.error_log = ""
                material.save(update_fields=["visual_slices", "status", "error_log", "modified"])

                logger.info(f"Refinement Successful: All {total_count} keyframes extracted and recorded.")

            except Exception as e:
                FrameExtractorService._handle_failure(material, e)
                raise

    @staticmethod
    def _parallel_extract_with_progress(video_path: Path, slices: list, abs_dir: Path, rel_dir: Path) -> list:
        total = len(slices)
        # 使用线程池进行物理抽帧
        # 工业化考量：max_workers=8 是 CPU 与 I/O 的平衡点
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            # 提交所有任务
            future_to_slice = {
                executor.submit(FrameExtractorService._extract_single_frame, video_path, s, abs_dir, rel_dir): i
                for i, s in enumerate(slices)
            }

            results = [None] * total
            completed = 0

            # 增量处理返回结果，每完成 10% 或 100 个打印一次进度
            for future in concurrent.futures.as_completed(future_to_slice):
                index = future_to_slice[future]
                try:
                    results[index] = future.result()
                except Exception as exc:
                    logger.error(f"Slice index {index} generated an exception: {exc}")
                    results[index] = slices[index]  # 失败则保留原样

                completed += 1
                if completed % 100 == 0 or completed == total:
                    percent = (completed / total) * 100
                    logger.info(f"Extraction Progress: {completed}/{total} ({percent:.1f}%)")  # noqa E231

            return results

    @staticmethod
    def _extract_single_frame(video_path: Path, s: dict, abs_dir: Path, rel_dir: Path) -> dict:
        """底层原子操作：单帧提取"""
        mid_time = (s["start_time"] + s["end_time"]) / 2
        file_name = f"slice_{s['slice_id']:04d}_mid.jpg"  # noqa E231
        abs_path = abs_dir / file_name
        rel_path = str(rel_dir / file_name).replace("\\", "/")

        # 使用 ffmpeg 快速定位
        cmd = [
            "ffmpeg",
            "-ss",
            str(round(mid_time, 3)),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "4",  # 工业化考量：q:v=4 兼顾清晰度与文件大小
            "-y",
            str(abs_path),
        ]

        # 吞掉 stdout/stderr 除非报错，保持日志清洁
        subprocess.run(cmd, capture_output=True, check=True, timeout=10)
        s["frames"] = [{"position": "mid", "path": rel_path}]
        return s

    @staticmethod
    def _handle_failure(material, error):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        material.handle_failure(f"[{timestamp}] Frame Extraction Error: {str(error)}")
        material.save(update_fields=["status", "error_log", "modified"])
