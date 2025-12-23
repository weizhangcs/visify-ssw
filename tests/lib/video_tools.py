# tests/lib/video_tools.py
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def cut_scenes_from_video(video_path: Path, scenes: List[Dict], slices: List[Dict], output_dir: Path):
    """
    [Validation Tool] 根据 AI 推理出的场景列表，物理切割视频以便人工验收
    """
    if not scenes or not slices:
        logger.warning("⚠️ No scenes or slice data to cut.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

    # 1. 建立查找表: Slice ID -> Slice Data
    # 兼容对象访问和字典访问
    slice_map = {}
    for s in slices:
        s_id = s.get("slice_id") if isinstance(s, dict) else s.slice_id
        slice_map[s_id] = s

    logger.info(f"✂️  Starting Physical Cutting for {len(scenes)} Scenes...")

    success_count = 0

    for i, sc in enumerate(scenes):
        # 兼容字典和对象
        idx = sc.get("index", i) if isinstance(sc, dict) else getattr(sc, "index", i)
        start_id = sc.get("start_slice_id") if isinstance(sc, dict) else getattr(sc, "start_slice_id", None)
        end_id = sc.get("end_slice_id") if isinstance(sc, dict) else getattr(sc, "end_slice_id", None)

        start_slice = slice_map.get(start_id)
        end_slice = slice_map.get(end_id)

        if not start_slice or not end_slice:
            logger.warning(f"  [Skip] Scene {idx}: Slice {start_id} or {end_id} not in map.")
            continue

        start_time = start_slice.get("start_time")
        end_time = end_slice.get("end_time")

        # 场景描述（如果有），用于文件名
        summary = sc.get("summary", "")[:20]  # 截取前20个字符
        safe_summary = "".join([c for c in summary if c.isalnum() or c in (" ", "_")]).strip().replace(" ", "_")

        filename = f"scene_{idx:03d}_{start_time:.0f}s_{end_time:.0f}s_{safe_summary}.mp4"  # noqa: E231
        out_path = output_dir / filename

        # 使用重编码模式 (-c:v libx264) 保证画面精准，而不是 -c copy (可能花屏)
        # -preset ultrafast 加速剪辑测试
        cmd = [
            ffmpeg_bin,
            "-y",
            "-ss",
            str(start_time),
            "-to",
            str(end_time),
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "copy",
            str(out_path),
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            print(f"  [OK] Saved: {filename}")
            success_count += 1
        except subprocess.CalledProcessError:
            print(f"  [Fail] Failed to cut scene {idx}")

    logger.info(f"📂 Cutting finished. {success_count}/{len(scenes)} clips saved to: {output_dir}")
