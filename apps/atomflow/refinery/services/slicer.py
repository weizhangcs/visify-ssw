# apps/atomflow/refinery/services/slicer.py
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List

from ..schemas import MultimodalSlice, SubtitleItem

logger = logging.getLogger(__name__)


class SlicingService:
    """
    [物理算子] 视觉切片服务。

    职责：
    1. 探测视频的视觉转场点 (Scene Changes)。
    2. 基于对白和声纹数据，计算切片的时间边界。
    3. 生成多模态切片 (MultimodalSlice) 结构。
    """

    @staticmethod
    def run(
        video_path: Path,
        video_duration: float,
        dialogue_track: List[Dict],
        waveform_data: List[float],
        # Optional Configs (Default values)
        scene_threshold: float = 0.3,
        dialogue_gap: float = 1.0,
        max_pad: float = 0.5,
        silence_thresh: float = 0.02,
    ) -> List[Dict]:
        """
        执行切片逻辑。

        Args:
            video_path: 视频文件路径。
            video_duration: 视频总时长。
            dialogue_track: 对白轨道数据。
            waveform_data: 音频波形数据。
            scene_threshold: 场景检测阈值 (0.0-1.0)。
            dialogue_gap: 对白合并的最大间隔 (秒)。
            max_pad: 切片前后填充的最大时长 (秒)。
            silence_thresh: 静音检测阈值。

        Returns:
            多模态切片字典列表 (List[MultimodalSlice.model_dump()])。
        """
        # 1. 物理执行：镜头变更探测 (基于 FFmpeg)
        scene_changes = SlicingService._detect_scene_changes(video_path, threshold=scene_threshold)

        # 2. 逻辑执行：对白分组 (合并紧凑对话，返回的 content 仅用于时间边界确定)
        grouped_dialogues = SlicingService._group_dialogues(dialogue_track, gap_threshold=dialogue_gap)

        # 3. 逻辑执行：基于声纹的动态 Padding (呼吸感)
        padded_dialogues = SlicingService._apply_waveform_padding(
            grouped_dialogues, waveform_data, video_duration, max_pad=max_pad, silence_thresh=silence_thresh
        )

        # 4. [核心重构] 构建多模态切片容器
        multimodal_slices = SlicingService._build_multimodal_slices(
            video_duration=video_duration,
            scene_changes=scene_changes,
            padded_dialogues=padded_dialogues,
            original_dialogue_track=dialogue_track,  # 传入原始轨道用于无损填充
        )

        return multimodal_slices

    @staticmethod
    def _detect_scene_changes(video_path: Path, threshold: float = 0.3) -> List[float]:
        """
        [内部方法] 使用 ffmpeg 探测视觉转场点。

        Args:
            video_path: 视频路径。
            threshold: 判定阈值。

        Returns:
            转场时间戳列表 (秒)。
        """
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
    def _group_dialogues(dialogue_track: List[Dict], gap_threshold: float = 1.0) -> List[Dict]:
        """
        [内部方法] 将间隔小于 gap_threshold 的对白合并为一个切片组。

        Args:
            dialogue_track: 原始对白列表。
            gap_threshold: 合并阈值。

        Returns:
            合并后的对白组列表 (仅包含时间边界)。
        """
        if not dialogue_track:
            return []

        sorted_track = sorted(dialogue_track, key=lambda x: x.get("start_time", 0))
        groups = []

        # 初始化第一个组
        current_group = sorted_track[0].copy()

        for next_item in sorted_track[1:]:
            gap = next_item.get("start_time", 0) - current_group.get("end_time", 0)

            # [优化] 不再拼接文本，只更新时间边界
            if gap < gap_threshold:
                # 合并
                current_group["end_time"] = next_item.get("end_time", 0)
            else:
                # 封存当前组，开启新组
                groups.append(current_group)
                current_group = next_item.copy()

        groups.append(current_group)
        return groups

    @staticmethod
    def _apply_waveform_padding(
        groups: List[Dict],
        waveform: List[float],
        duration: float,
        max_pad: float = 0.5,
        silence_thresh: float = 0.02,
    ) -> List[Dict]:
        """
        [内部方法] 基于声纹数据的动态 Padding (呼吸感)。
        在不覆盖相邻对白的前提下，向前后扩展切片边界，直到遇到静音或达到最大值。

        Args:
            groups: 对白组列表。
            waveform: 波形数据。
            duration: 视频总时长。
            max_pad: 最大填充时长。
            silence_thresh: 静音阈值。

        Returns:
            填充后的对白组列表。
        """
        if not waveform or duration <= 0:
            return groups

        # 计算声纹采样率 (ProbeService 默认 chunk_size=100, ar=8000 -> 80 peaks/sec)
        peaks_per_sec = len(waveform) / duration

        for i, group in enumerate(groups):
            start = group["start_time"]
            end = group["end_time"]

            # 1. 向前扩展 (Start Padding)
            # 限制：不能超过上一句的结束
            prev_end = groups[i - 1]["end_time"] if i > 0 else 0.0
            pad_start = 0.0
            # 步进扫描，直到遇到静音或达到最大值
            while pad_start < max_pad:
                check_time = start - pad_start - 0.05
                if check_time < prev_end:
                    break
                idx = int(check_time * peaks_per_sec)
                if 0 <= idx < len(waveform) and waveform[idx] < silence_thresh:
                    # 遇到静音，停止扩展（保留这部分静音作为呼吸空间）
                    pad_start += 0.05
                    break
                pad_start += 0.05

            group["start_time"] = max(prev_end, start - pad_start)

            # 2. 向后扩展 (End Padding)
            # 限制：不能超过下一句的开始
            next_start = groups[i + 1]["start_time"] if i < len(groups) - 1 else duration
            pad_end = 0.0
            while pad_end < max_pad:
                check_time = end + pad_end + 0.05
                if check_time > next_start:
                    break
                idx = int(check_time * peaks_per_sec)
                if 0 <= idx < len(waveform) and waveform[idx] < silence_thresh:
                    pad_end += 0.05
                    break
                pad_end += 0.05

            group["end_time"] = min(next_start, end + pad_end)

        return groups

    @staticmethod
    def _build_multimodal_slices(
        video_duration: float,
        scene_changes: List[float],
        padded_dialogues: List[Dict],
        original_dialogue_track: List[Dict],
    ) -> List[Dict]:
        """
        [内部方法] 构建多模态切片容器的三步流程。
        1. Temporal Segmentation: 结合对白和视觉转场，划分全覆盖的时间区间。
        2. Skeleton Creation: 创建 MultimodalSlice 对象。
        3. Text Hydration: 将原始对白填充回对应的切片中。

        Returns:
            序列化后的切片列表。
        """
        # --- 步骤 1: 定义时间区间 (Temporal Segmentation) ---
        temporal_segments = []
        last_time = 0.0

        for entry in padded_dialogues:
            start_sec, end_sec = float(entry.get("start_time", 0)), float(entry.get("end_time", 0))

            # Gap Filling
            if start_sec > last_time:
                internal_cuts = [t for t in scene_changes if last_time + 0.5 < t < start_sec - 0.5]
                ptr = last_time
                for cut in internal_cuts:
                    temporal_segments.append({"start": ptr, "end": cut, "type": "visual_segment"})
                    ptr = cut
                temporal_segments.append({"start": ptr, "end": start_sec, "type": "visual_segment"})

            # Dialogue Segment
            temporal_segments.append({"start": start_sec, "end": end_sec, "type": "dialogue"})
            last_time = end_sec

        # Tail Gap
        if last_time < video_duration:
            temporal_segments.append({"start": last_time, "end": video_duration, "type": "visual_segment"})

        # --- 步骤 2: 创建容器骨架 (Skeleton Creation) ---
        multimodal_slices = []
        for i, seg in enumerate(temporal_segments):
            slice_obj = MultimodalSlice(
                slice_id=i + 1,
                start_time=round(seg["start"], 3),
                end_time=round(seg["end"], 3),
                type=seg["type"],
            )
            multimodal_slices.append(slice_obj)

        # --- 步骤 3: 填充文本内容 (Text Hydration) ---
        # 预处理原始字幕，方便快速查找
        subtitle_map = {item["index"]: item for item in original_dialogue_track}  # noqa: F841

        for m_slice in multimodal_slices:
            if m_slice.type == "dialogue":
                # 筛选出时间戳落在该切片内的所有原始字幕行
                contained_subtitles = []
                for sub_item_data in original_dialogue_track:
                    sub_start = sub_item_data.get("start_time", 0)
                    if m_slice.start_time <= sub_start < m_slice.end_time:
                        # 使用 Pydantic 模型进行校验和实例化
                        contained_subtitles.append(SubtitleItem(**sub_item_data))

                m_slice.text_contents = contained_subtitles

        # 返回序列化后的字典列表
        return [s.model_dump() for s in multimodal_slices]
