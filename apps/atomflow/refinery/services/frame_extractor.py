# apps/atomflow/refinery/services/frame_extractor.py
import concurrent.futures
import hashlib
import logging
import re
import subprocess
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

from apps.common.schemas.dataset.schemas import KeyframeItem, Slice

logger = logging.getLogger(__name__)


class FrameExtractorService:
    """
    [物理算子] 关键帧提取服务。

    职责：
    1. 接收视觉切片列表。
    2. 对每个切片进行智能抽帧 (首尾帧 + 内部变化帧)。
    3. 使用 FFmpeg 提取物理图片文件。
    4. 计算文件摘要 (Digest)。
    5. 返回结构化的关键帧映射表 (keyframe_map)。
    """

    @staticmethod
    def run(video_path: Path, slices: List[Dict], abs_output_dir: Path, rel_output_dir: Path) -> Dict[str, List[Dict]]:
        """
        执行大规模抽帧任务。

        Args:
            video_path: 视频文件路径 (Proxy)。
            slices: 切片清单 (List[MultimodalSlice.model_dump()])。
            abs_output_dir: 图片存储的物理绝对路径。
            rel_output_dir: 存入数据库的相对路径前缀。

        Returns:
            keyframe_map: 字典，Key 为 slice_id (str)，Value 为 FrameDataInput 列表。
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

            results_map = {}  # 存储 keyframe_map 的结果
            completed = 0
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    slice_id_str, extracted_frames_list = future.result()
                    results_map[slice_id_str] = extracted_frames_list
                except Exception as e:
                    logger.error(f"Frame Extraction Failed for slice index {index}: {str(e)}")
                    # 失败则返回空列表，不阻断其他切片
                    # 尝试从原始数据中恢复 slice_id 以保持 map 结构完整
                    try:
                        slice_id_str = str(Slice(**slices[index]).slice_id)
                        results_map[slice_id_str] = []
                    except Exception:
                        pass

                completed += 1
                if completed % 50 == 0 or completed == total:
                    logger.info(
                        f"Extraction Progress: {completed}/{total} ({(completed / total) * 100:.1f}%)"  # noqa: E231
                    )

            return results_map

    @staticmethod
    def _extract_single_frame(
        video_path: Path, slice_data: Dict, abs_dir: Path, rel_dir: Path
    ) -> Tuple[str, List[Dict]]:
        """
        [内部方法] 处理单个切片的抽帧逻辑。

        策略：
        1. 总是抽取切片的首帧。
        2. 如果切片长度 > 1s，抽取尾帧。
        3. 使用 ffmpeg select 过滤器检测内部显著变化点，并抽取。
        4. 如果无内部变化且切片较长 (> 2s)，抽取中间帧保底。

        Args:
            video_path: 视频路径。
            slice_data: 单个切片数据。
            abs_dir: 输出目录。
            rel_dir: 相对路径前缀。

        Returns:
            (slice_id_str, List[FrameDataInput.model_dump()])
        """
        slice_obj = Slice(**slice_data)

        start_time = slice_obj.start_time
        end_time = slice_obj.end_time
        slice_id_str = str(slice_obj.id)  # [Phase 1] 使用 UUID

        # 1. 检测切片内部的视觉变化点
        internal_changes = FrameExtractorService._detect_internal_visual_changes(video_path, start_time, end_time)

        # 2. 确定要抽取的帧的时间点和原因
        frame_timestamps = []

        # 总是抽取首帧和尾帧 (如果切片足够长)
        frame_timestamps.append({"time": start_time, "reason": "slice_boundary"})
        if end_time - start_time > 1.0:
            frame_timestamps.append({"time": end_time, "reason": "slice_boundary"})

        # 加入内部变化点
        for t in internal_changes:
            frame_timestamps.append({"time": t, "reason": "internal_scene_change"})

        # 如果没有任何变化点，且切片较长，则抽取中点作为保底
        if not internal_changes and end_time - start_time > 2.0:
            mid_time = (start_time + end_time) / 2
            frame_timestamps.append({"time": mid_time, "reason": "fallback_mid"})

        # 去重并排序
        unique_frames_to_extract = sorted(
            list({(round(f["time"], 3), f["reason"]) for f in frame_timestamps}), key=lambda x: x[0]
        )

        extracted_frame_inputs = []
        for i, (timestamp, reason) in enumerate(unique_frames_to_extract):
            file_name = f"slice_{slice_obj.index:04d}_{reason}_{i:02d}.jpg"  # noqa: E231
            abs_path = abs_dir / file_name
            rel_path = str(rel_dir / file_name).replace("\\", "/")

            cmd = [
                "ffmpeg",
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-color_range",
                "tv",
                "-pix_fmt",
                "yuvj420p",
                "-q:v",
                "4",
                "-y",
                str(abs_path),
            ]

            try:
                subprocess.run(cmd, capture_output=True, check=True, timeout=30)

                if not abs_path.exists():
                    logger.warning(
                        f"FFmpeg did not produce an output file for slice {slice_id_str} at {timestamp}s. Skipping."
                    )
                    continue

                digest = FrameExtractorService._calculate_file_hash(abs_path)

                extracted_frame_inputs.append(
                    KeyframeItem(
                        id=str(uuid.uuid4()),  # [Phase 1] UUID
                        timestamp=timestamp,
                        path=rel_path,
                        reason=reason,
                        slice_id=slice_obj.id,  # [Phase 1] 引用 Slice UUID
                        digest=digest,
                    ).model_dump()
                )
            except subprocess.TimeoutExpired:
                logger.error(f"FFmpeg Timeout for slice {slice_id_str} at {timestamp}s")
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else "Unknown FFmpeg error"
                logger.error(f"FFmpeg Error for slice {slice_id_str} at {timestamp}s: {error_msg}")
            except Exception as e:
                logger.error(f"Frame Extraction Unexpected Error for slice {slice_id_str} at {timestamp}s: {str(e)}")

        return slice_id_str, extracted_frame_inputs

    @staticmethod
    def _detect_internal_visual_changes(video_path: Path, start_time: float, end_time: float) -> List[float]:
        """
        [内部方法] 使用 ffmpeg select 过滤器检测切片内部的场景变化点。

        Args:
            video_path: 视频路径。
            start_time: 检测起始时间。
            end_time: 检测结束时间。

        Returns:
            变化点时间戳列表 (绝对时间)。
        """
        # 阈值 0.1 比 Slicer 的 0.3 更敏感，用于捕捉切片内部的微小变化
        threshold = 0.3
        filter_chain = f"select='gt(scene,{threshold})',showinfo"  # noqa: E231

        cmd = [
            "ffmpeg",
            "-ss",
            str(start_time),
            "-to",
            str(end_time),
            "-i",
            str(video_path),
            "-vf",
            filter_chain,
            "-f",
            "null",
            "-",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="ignore")

            timestamps = []
            for line in result.stderr.splitlines():
                if "pts_time:" in line and "showinfo" in line:
                    match = re.search(r"pts_time:([0-9.]+)", line)
                    if match:
                        t_rel = float(match.group(1))
                        t_abs = start_time + t_rel
                        if start_time < t_abs < end_time:
                            timestamps.append(t_abs)

            return sorted(list(set(timestamps)))
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else "FFmpeg error (no details)"
            logger.warning(f"FFmpeg Internal Scene Detection Failed for slice ({start_time}-{end_time}s): {error_msg}")
            return []

    @staticmethod
    def _calculate_file_hash(file_path: Path, algorithm: str = "md5") -> str:
        """
        [内部方法] 计算文件的哈希摘要。
        """
        hash_func = getattr(hashlib, algorithm)()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
