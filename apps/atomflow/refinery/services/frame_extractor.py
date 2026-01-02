# apps/atomflow/refinery/services/frame_extractor.py
import concurrent.futures
import logging
import subprocess
from pathlib import Path
from typing import Dict, List

from ..schemas import FrameData

logger = logging.getLogger(__name__)


class FrameExtractorService:
    @staticmethod
    def run(video_path: Path, slices: List[Dict], abs_output_dir: Path, rel_output_dir: Path) -> List[Dict]:
        """
        [物理算子] 大规模抽帧
        输入：
            video_path: Proxy 绝对路径
            slices: 切片清单 (JSONB 结构)
            abs_output_dir: 图片存储的物理绝对路径
            rel_output_dir: 存入数据库的相对路径前缀
        """
        abs_output_dir.mkdir(parents=True, exist_ok=True)
        total = len(slices)
        logger.info(f"Frame Extraction Start: {total} slices from {video_path.name}")

        # 使用线程池加速 I/O 密集型任务 (FFmpeg 快速定位抽帧)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_index = {
                executor.submit(
                    FrameExtractorService._extract_single_frame, video_path, s, abs_output_dir, rel_output_dir
                ): i
                for i, s in enumerate(slices)
            }

            results = [None] * total
            completed = 0
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    logger.error(f"Frame Extraction Failed for slice index {index}: {str(e)}")
                    results[index] = slices[index]  # 失败则保留原样，防止整批任务崩溃

                completed += 1
                if completed % 50 == 0 or completed == total:
                    logger.info(
                        f"Extraction Progress: {completed}/{total} ({(completed / total) * 100:.1f}%)"  # noqa: E231
                    )

            return results

    @staticmethod
    def _extract_single_frame(video_path: Path, slice_data: Dict, abs_dir: Path, rel_dir: Path) -> Dict:
        """底层原子操作：FFmpeg 精确时间点抽帧"""
        # 取切片中间点时间
        mid_time = (slice_data["start_time"] + slice_data["end_time"]) / 2
        file_name = f"slice_{slice_data['slice_id']:04d}_mid.jpg"  # noqa: E231
        abs_path = abs_dir / file_name

        # 数据库存储路径对齐：rel_dir (如 frames/uuid) + file_name
        rel_path = str(rel_dir / file_name).replace("\\", "/")

        cmd = [
            "ffmpeg",
            "-ss",
            str(round(mid_time, 3)),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "4",
            "-y",
            str(abs_path),
        ]

        try:
            # 抽帧操作必须设置 timeout，防止某些损坏视频导致线程永久挂起
            subprocess.run(cmd, capture_output=True, check=True, timeout=15)
            # [Fix] 更新 visual_contents.frames
            frame = FrameData(position="mid", path=rel_path)
            slice_data["visual_contents"]["frames"] = [frame.model_dump()]
            return slice_data
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else "FFmpeg error"
            raise RuntimeError(f"FFmpeg Single Frame Extraction Failed: {error_msg}")
