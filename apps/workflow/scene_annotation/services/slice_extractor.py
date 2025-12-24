import concurrent.futures
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .core_slicer_ass import VSSASSSlicer

logger = logging.getLogger(__name__)


class SliceExtractorService:
    def __init__(self, output_root: Path, max_workers: int = 4):
        self.output_root = output_root
        self.frames_dir = output_root / "frames"
        self.ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        self.max_workers = max_workers

    def run(self, video_path: str, ass_path: str) -> List[Dict[str, Any]]:
        if not self.frames_dir.exists():
            self.frames_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting VSSASSSlicer for {video_path}")
        slicer = VSSASSSlicer(video_path, ass_path)
        compute_result = slicer.compute_slices()
        raw_slices = compute_result["slices"]

        total_slices = len(raw_slices)
        logger.info(f"Generated {total_slices} slices. Extracting frames...")

        processed_slices = []

        # 传递 video_path 给 worker
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_slice = {
                executor.submit(self._extract_frames, item, Path(video_path)): item for item in raw_slices
            }

            completed = 0
            for future in concurrent.futures.as_completed(future_to_slice):
                item = future_to_slice[future]
                try:
                    frames = future.result()
                    item["frames"] = frames
                except Exception as e:
                    logger.error(f"Slice {item['slice_id']} failed: {e}")
                    item["frames"] = []

                processed_slices.append(item)
                completed += 1
                if completed % 50 == 0:
                    logger.info(f"Processed {completed}/{total_slices}...")

        processed_slices.sort(key=lambda x: x["slice_id"])
        return processed_slices

    def _extract_frames(self, slice_data: Dict, video_path: Path) -> List[Dict[str, Any]]:
        start = slice_data["start_time"]
        end = slice_data["end_time"]
        slice_id = slice_data["slice_id"]

        # 极短片段只取中间帧
        if end - start < 1.0:
            points = [("mid", start + (end - start) / 2)]
        else:
            points = [("start", start), ("mid", start + (end - start) / 2), ("end", end)]

        frames_info = []
        for label, ts in points:
            # 规范命名：slice_0001_mid.jpg
            filename = f"slice_{slice_id:04d}_{label}.jpg"  # noqa: E231
            out_path = self.frames_dir / filename

            # 使用 ffmpeg 快速定位截图 (-ss 在 -i 前)
            if not out_path.exists():
                cmd = [
                    self.ffmpeg_bin,
                    "-y",
                    "-ss",
                    f"{ts:.3f}",  # noqa: E231
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",  # 质量控制
                    str(out_path),
                ]
                try:
                    # 增加 timeout=10，防止单个 ffmpeg 进程卡死
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Timeout extracting frame at {ts}s for slice {slice_id}")

            if out_path.exists():
                frames_info.append({"position": label, "timestamp": round(ts, 3), "path": str(out_path.absolute())})

        return frames_info
