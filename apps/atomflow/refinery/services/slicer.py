# apps/atomflow/refinery/services/slicer.py
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List

from ..schemas import VisualSliceItem

logger = logging.getLogger(__name__)


class SlicingService:
    @staticmethod
    def run(video_path: Path, video_duration: float, dialogue_track: List[Dict]) -> List[Dict]:
        """
        [物理算子] 视觉切片逻辑
        职责：1. 镜头探测 2. 时间轴合并算法
        输入：视频路径, 视频时长, 对白列表
        输出：切片清单 (List[Dict])
        """
        # 1. 物理执行：镜头变更探测 (基于 FFmpeg)
        scene_changes = SlicingService._detect_scene_changes(video_path)

        # 2. 纯逻辑执行：区间合并算法
        slices_manifest = SlicingService._compute_slices_logic(
            video_duration=video_duration, scene_changes=scene_changes, dialogue_track=dialogue_track
        )

        return slices_manifest

    @staticmethod
    def _detect_scene_changes(video_path: Path) -> List[float]:
        """[物理镜像] 使用 ffmpeg 探测视觉转场点"""
        threshold = 0.3
        filter_chain = f"[0:v]select='gt(scene,{threshold})',showinfo[outv]"  # noqa: E231
        cmd = ["ffmpeg", "-i", str(video_path), "-filter_complex", filter_chain, "-map", "[outv]", "-f", "null", "-"]

        logger.info(f"FFmpeg Scene Detect Start: {video_path.name}")
        try:
            # 捕获 stderr，因为 showinfo 的输出在 stderr
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="ignore")

            timestamps = []
            for line in result.stderr.splitlines():
                if "pts_time:" in line and "showinfo" in line:
                    match = re.search(r"pts_time:([0-9.]+)", line)
                    if match:
                        timestamps.append(float(match.group(1)))

            return sorted(list(set(timestamps)))
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg Scene Detection Physical Error: {e.stderr}")
            raise RuntimeError(f"FFmpeg Scene Detection Failed: {e.stderr}")

    @staticmethod
    def _compute_slices_logic(
        video_duration: float, scene_changes: List[float], dialogue_track: List[Dict]
    ) -> List[Dict]:
        """[纯算法] 核心时间轴合并逻辑 (代码逻辑同原版，仅去除依赖)"""
        MIN_VISUAL_DURATION = 2.0
        slices = []
        last_time = 0.0
        # [Fix] 字段名修正：对齐 SubtitleItem Schema (start -> start_time)
        sorted_dialogues = sorted(dialogue_track, key=lambda x: x.get("start_time", 0))

        for entry in sorted_dialogues:
            # [Fix] 字段名修正：start -> start_time, end -> end_time, text -> content
            start_sec, end_sec = float(entry.get("start_time", 0)), float(entry.get("end_time", 0))
            text, speaker = entry.get("content", ""), entry.get("speaker", "Unknown")

            # Gap Filling
            if start_sec > last_time and (start_sec - last_time) >= MIN_VISUAL_DURATION:
                internal_cuts = [t for t in scene_changes if last_time + 0.5 < t < start_sec - 0.5]
                ptr = last_time
                for cut in internal_cuts:
                    slices.append(
                        VisualSliceItem(
                            slice_id=0,  # 稍后统一更新
                            start_time=round(ptr, 3),
                            end_time=round(cut, 3),
                            type="visual_segment",
                            text_content=None,
                        ).model_dump()
                    )
                    ptr = cut

                slices.append(
                    VisualSliceItem(
                        slice_id=0,
                        start_time=round(ptr, 3),
                        end_time=round(start_sec, 3),
                        type="visual_segment",
                        text_content=None,
                    ).model_dump()
                )

            # Dialogue Segment
            slices.append(
                VisualSliceItem(
                    slice_id=0,
                    start_time=round(start_sec, 3),
                    end_time=round(end_sec, 3),
                    type="dialogue",
                    text_content=f"[{speaker}]: {text}",
                ).model_dump()
            )
            last_time = end_sec

        # Tail Gap
        if last_time < video_duration and (video_duration - last_time) >= MIN_VISUAL_DURATION:
            slices.append(
                VisualSliceItem(
                    slice_id=0,
                    start_time=round(last_time, 3),
                    end_time=round(video_duration, 3),
                    type="visual_segment",
                    text_content=None,
                ).model_dump()
            )

        for idx, s in enumerate(slices):
            s["slice_id"] = idx + 1
        return slices
