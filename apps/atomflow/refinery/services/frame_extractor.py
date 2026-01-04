# apps/atomflow/refinery/services/frame_extractor.py
import concurrent.futures
import hashlib
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from ..schemas import FrameDataInput, MultimodalSlice

logger = logging.getLogger(__name__)


class FrameExtractorService:
    @staticmethod
    def run(video_path: Path, slices: List[Dict], abs_output_dir: Path, rel_output_dir: Path) -> Dict[str, List[Dict]]:
        """
        [物理算子] 大规模抽帧
        输入：
            video_path: Proxy 绝对路径
            slices: 切片清单 (JSONB 结构)
            abs_output_dir: 图片存储的物理绝对路径
            rel_output_dir: 存入数据库的相对路径前缀
        """
        abs_output_dir.mkdir(parents=True, exist_ok=True)  # 确保输出目录存在
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
                    slice_id_str = MultimodalSlice(**slices[index]).slice_id
                    results_map[str(slice_id_str)] = []

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
        [核心重构] 智能抽帧逻辑：根据切片内容动态决定抽帧策略
        """
        slice_obj = MultimodalSlice(**slice_data)  # 确保数据结构正确

        start_time = slice_obj.start_time
        end_time = slice_obj.end_time
        slice_id_str = str(slice_obj.slice_id)  # keyframe_map 的键是字符串

        # 1. 检测切片内部的视觉变化点
        internal_changes = FrameExtractorService._detect_internal_visual_changes(video_path, start_time, end_time)

        # 2. 确定要抽取的帧的时间点和原因
        frame_timestamps = []

        # 总是抽取首帧和尾帧 (如果切片足够长)
        frame_timestamps.append({"time": start_time, "reason": "slice_boundary"})
        if end_time - start_time > 1.0:  # 避免过短切片重复抽帧
            frame_timestamps.append({"time": end_time, "reason": "slice_boundary"})

        # 加入内部变化点
        for t in internal_changes:
            frame_timestamps.append({"time": t, "reason": "internal_scene_change"})

        # 如果没有任何变化点，且切片较长，则抽取中点作为保底
        if not internal_changes and end_time - start_time > 2.0:
            mid_time = (start_time + end_time) / 2
            frame_timestamps.append({"time": mid_time, "reason": "fallback_mid"})

        # 去重并排序 (时间点可能重复)
        unique_frames_to_extract = sorted(
            list({(round(f["time"], 3), f["reason"]) for f in frame_timestamps}), key=lambda x: x[0]
        )

        extracted_frame_inputs = []  # 存储 FrameDataInput
        for i, (timestamp, reason) in enumerate(unique_frames_to_extract):
            file_name = f"slice_{slice_obj.slice_id:04d}_{reason}_{i:02d}.jpg"  # noqa: E231
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
                "tv",  # 明确指定颜色范围为电视标准，处理非标准YUV输入
                "-pix_fmt",
                "yuvj420p",  # 明确输出像素格式为JPEG兼容的YUV420P
                "-q:v",
                "4",  # 质量参数，1-5，1最好
                "-y",
                str(abs_path),
            ]

            try:
                subprocess.run(cmd, capture_output=True, check=True, timeout=30)  # 增加超时时间

                # [Fix] 验证 FFmpeg 是否成功生成了文件，处理视频末尾抽帧失败的边缘情况
                if not abs_path.exists():
                    logger.warning(
                        f"FFmpeg did not produce an output file for slice {slice_id_str} at {timestamp}s. Skipping this frame."  # noqa: E501
                    )
                    continue

                # [New] 计算文件摘要 (MD5)
                digest = FrameExtractorService._calculate_file_hash(abs_path)

                extracted_frame_inputs.append(
                    FrameDataInput(
                        timestamp=timestamp, path=rel_path, reason=reason, slice_id=slice_obj.slice_id, digest=digest
                    ).model_dump()
                )
            except subprocess.TimeoutExpired:
                logger.error(f"FFmpeg Timeout for slice {slice_id_str} at {timestamp}s")
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr.decode() if e.stderr else "Unknown FFmpeg error"
                logger.error(f"FFmpeg Error for slice {slice_id_str} at {timestamp}s: {error_msg}")
            except Exception as e:
                logger.error(f"Frame Extraction Unexpected Error for slice {slice_id_str} at {timestamp}s: {str(e)}")
            # 即使单帧失败，也继续循环处理其他帧

        # 返回 slice_id 和其对应的 FrameDataInput 列表
        return slice_id_str, extracted_frame_inputs

    @staticmethod
    def _detect_internal_visual_changes(video_path: Path, start_time: float, end_time: float) -> List[float]:
        """
        使用 ffmpeg select 过滤器检测切片内部的场景变化点。
        阈值比 Slicer 更敏感，以捕捉更多细节。
        """
        # 阈值 0.1 比 Slicer 的 0.3 更敏感，用于捕捉切片内部的微小变化
        threshold = 0.3
        filter_chain = f"select='gt(scene,{threshold})',showinfo"  # noqa: E231

        cmd = [
            "ffmpeg",
            "-ss",
            str(start_time),  # 从切片开始时间开始检测
            "-to",
            str(end_time),  # 到切片结束时间结束检测
            "-i",
            str(video_path),
            "-vf",
            filter_chain,
            "-f",
            "null",
            "-",
        ]

        try:  # 增加超时时间
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="ignore")

            timestamps = []
            for line in result.stderr.splitlines():
                if "pts_time:" in line and "showinfo" in line:
                    match = re.search(r"pts_time:([0-9.]+)", line)
                    if match:
                        t_rel = float(match.group(1))
                        t_abs = start_time + t_rel  # [Fix] 将相对时间转换为绝对时间
                        # 确保时间戳在切片内部，避免边界误差
                        if start_time < t_abs < end_time:
                            timestamps.append(t_abs)

            return sorted(list(set(timestamps)))
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else "FFmpeg error (no details)"
            logger.warning(f"FFmpeg Internal Scene Detection Failed for slice ({start_time}-{end_time}s): {error_msg}")
            return []  # 不阻断流程，返回空列表

    @staticmethod
    def _calculate_file_hash(file_path: Path, algorithm: str = "md5") -> str:
        """计算文件的哈希摘要"""
        hash_func = getattr(hashlib, algorithm)()
        with open(file_path, "rb") as f:
            # 分块读取，虽然图片很小，但保持好习惯
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
