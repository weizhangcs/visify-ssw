# 文件路径: apps/refinery/services/slicing.py

import logging
import re
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from django.conf import settings
from django.db import transaction

# 获取标准日志记录器
logger = logging.getLogger(__name__)


class SlicingService:
    """
    [原子服务] 视觉切片逻辑精炼 (镜像版)
    职责：基于镜头检测和数据库中的结构化对白，计算切片清单。
    输入：Material.proxy_video (路径), Material.dialogue_track (JSONB)
    产出：Material.visual_slices (JSONB)
    """

    @staticmethod
    def execute_and_report(material_id: str):
        from apps.refinery.models import Material

        try:
            with transaction.atomic():
                # 锁定行，确保 FSM 状态一致性
                material = Material.objects.select_for_update().get(id=material_id)

                # --- 1. 准入校验 ---
                if not material.proxy_video:
                    raise ValueError(f"Slicing Failed: Material {material_id} 缺失 Proxy 视频。")

                # 获取绝对路径用于物理计算
                video_abs_path = Path(settings.MEDIA_ROOT) / material.proxy_video
                if not video_abs_path.exists():
                    raise FileNotFoundError(f"Proxy 物理文件未找到: {video_abs_path}")

                logger.info(f"Refinement Started: Calculating visual slices for {material_id}")

                # --- 2. 物理执行 A: 镜头变更探测 (镜像 FFmpeg 逻辑) ---
                scene_changes = SlicingService._detect_scene_changes(video_abs_path)

                # --- 3. 物理执行 B: 区间合并 (镜像计算算法) ---
                # 核心改变：此处直接传入数据库中的 dialogue_track
                slices_manifest = SlicingService._compute_slices_logic(
                    video_duration=material.duration,
                    scene_changes=scene_changes,
                    dialogue_track=material.dialogue_track or [],
                )

                # --- 4. 数据落地 ---
                material.visual_slices = slices_manifest

                # --- 5. 范式回归 ---
                if material.status == material.Status.SLICING:
                    material.finish_current_task()

                material.error_log = ""
                material.save(update_fields=["visual_slices", "status", "error_log", "modified"])

                logger.info(f"Refinement Successful: {len(slices_manifest)} slices defined for {material_id}")

        except subprocess.CalledProcessError as e:
            SlicingService._handle_failure(
                material_id, f"FFmpeg Scene Detection Failed (Code {e.returncode}): \n{e.stderr}"
            )
            raise
        except Exception as e:
            SlicingService._handle_failure(material_id, f"Slicing Service Error: {str(e)}\n{traceback.format_exc()}")
            raise

    @staticmethod
    def _detect_scene_changes(video_path: Path) -> List[float]:
        """[镜像] 使用 ffmpeg 探测视觉转场点"""
        threshold = 0.3  # 镜像存量参数
        # 构造滤镜命令：探测变化大于 0.3 的场景并输出 showinfo
        filter_chain = f"[0:v]select='gt(scene,{threshold})',showinfo[outv]"  # noqa E231
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-filter_complex",
            filter_chain,
            "-map",
            "[outv]",  # 显式映射输出标签
            "-f",
            "null",
            "-",
        ]

        logger.info(f"FFmpeg Scene Detect CMD: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="ignore")

        timestamps = []
        # 正则提取 pts_time
        for line in result.stderr.splitlines():
            if "pts_time:" in line and "showinfo" in line:
                match = re.search(r"pts_time:([0-9.]+)", line)
                if match:
                    timestamps.append(float(match.group(1)))

        unique_ts = sorted(list(set(timestamps)))
        return unique_ts

    @staticmethod
    def _compute_slices_logic(
        video_duration: float, scene_changes: List[float], dialogue_track: List[Dict]
    ) -> List[Dict]:
        """
        [镜像] 核心时间轴合并算法
        将“视觉转场”与“结构化对白”合并为原子切片清单。
        """
        MIN_VISUAL_DURATION = 2.0  # 镜像自存量配置
        slices = []
        last_time = 0.0

        # 按开始时间排序对白
        sorted_dialogues = sorted(dialogue_track, key=lambda x: x.get("start", 0))

        for entry in sorted_dialogues:
            start_sec = float(entry.get("start", 0))
            end_sec = float(entry.get("end", 0))
            text = entry.get("text", "")
            speaker = entry.get("speaker", "Unknown")

            # --- Logic A: Gap Filling (视觉空隙填充) ---
            if start_sec > last_time:
                gap_start = last_time
                gap_end = start_sec

                if (gap_end - gap_start) >= MIN_VISUAL_DURATION:
                    # 寻找落在 Gap 内部的转场点 (避开边缘 0.5s)
                    internal_cuts = [t for t in scene_changes if gap_start + 0.5 < t < gap_end - 0.5]

                    ptr = gap_start
                    if internal_cuts:
                        for cut in internal_cuts:
                            slices.append(
                                {
                                    "start_time": round(ptr, 3),
                                    "end_time": round(cut, 3),
                                    "type": "visual_segment",
                                    "text_content": None,
                                }
                            )
                            ptr = cut

                    # 收尾 Gap
                    slices.append(
                        {
                            "start_time": round(ptr, 3),
                            "end_time": round(gap_end, 3),
                            "type": "visual_segment",
                            "text_content": None,
                        }
                    )

            # --- Logic B: Dialogue (对白片段) ---
            slices.append(
                {
                    "start_time": round(start_sec, 3),
                    "end_time": round(end_sec, 3),
                    "type": "dialogue",
                    "text_content": f"[{speaker}]: {text}",
                }
            )
            last_time = end_sec

        # --- Logic C: Tail Gap (片尾处理) ---
        if last_time < video_duration and (video_duration - last_time) >= MIN_VISUAL_DURATION:
            slices.append(
                {
                    "start_time": round(last_time, 3),
                    "end_time": round(video_duration, 3),
                    "type": "visual_segment",
                    "text_content": None,
                }
            )

        # 统一生成 Slice ID (1-based)
        for idx, s in enumerate(slices):
            s["slice_id"] = idx + 1

        return slices

    @staticmethod
    def _handle_failure(material_id: str, error_msg: str):
        """工业化失败处理记录"""
        from apps.refinery.models import Material

        try:
            material = Material.objects.get(id=material_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_error = f"[{timestamp}] Slicing Logic Stage Failed: \n{error_msg}"
            logger.error(f"Slicing Refinement ERROR for {material_id}: {formatted_error}")
            material.handle_failure(formatted_error)
            material.save(update_fields=["status", "error_log", "modified"])
        except Exception:
            pass
