# 文件路径: apps/refinery/services/probe.py

import json
import logging
import os
import subprocess
from datetime import datetime
from typing import Dict, List, Tuple

from django.db import transaction

logger = logging.getLogger(__name__)


class ProbeService:
    @staticmethod
    def execute_and_report(material_id: str):
        """
        [原子服务] 媒体物理探测与声纹精炼
        职责：
        1. ffprobe 获取元数据与时长。
        2. 镜像集成声纹计算，结果直接存入 JSONB 字段。
        """
        from apps.refinery.models import Material

        try:
            with transaction.atomic():
                # 锁定行，确保 FSM 状态机执行环境安全
                material = Material.objects.select_for_update().get(id=material_id)
                video_path = material.media.source_video.path

                # --- Step 1: 物理探测 (Metadata) ---
                logger.info(f"Refinement: Probing metadata for Material {material_id}")
                tech_meta, duration = ProbeService._probe_file(video_path)
                material.tech_meta = tech_meta
                material.duration = duration

                # --- Step 2: 声纹精炼 (Waveform - 物理镜像集成) ---
                # 提取声纹通常涉及 CPU 计算，符合异步任务特性
                logger.info(f"Refinement: Generating waveform peaks for Material {material_id}")
                waveform_list = ProbeService._generate_peaks_in_memory(video_path)

                if waveform_list:
                    # 关键修改：直接存入 JSONB 字段，不保存物理文件
                    material.waveform_data = {"version": 1, "sample_rate": 8000, "data": waveform_list}
                else:
                    logger.warning(f"Waveform generation returned empty data for {material_id}")

                # --- Step 3: 范式回归 ---
                if material.status == material.Status.PROBING:
                    material.finish_current_task()

                material.error_log = ""  # 成功清除错误日志
                material.save(
                    update_fields=["tech_meta", "duration", "waveform_data", "status", "error_log", "modified"]
                )

                # 同步更新 Media 时长（利旧兼容）
                material.media.duration = duration
                material.media.save(update_fields=["duration"])

                logger.info(f"Refinement Successful: Metadata & Waveform ready for {material_id}")

        except Exception as e:
            # 工业化处理：透传异常至 DB 和日志
            ProbeService._handle_failure(material_id, e)
            raise

    @staticmethod
    def _generate_peaks_in_memory(video_path: str) -> List[float]:
        """
        [物理镜像] 核心声纹采样算法。
        镜像自存量 utils 逻辑，并优化为内存友好的处理。
        """
        try:
            import numpy as np
            from pydub import AudioSegment
        except ImportError:
            logger.error("Dependency missing: numpy or pydub not found in worker environment.")
            return []

        # 使用 PID 命名防止并发任务冲突
        temp_wav = f"/tmp/refinery_wf_{os.getpid()}.wav"
        try:
            # 1. 快速提取低采样音频流
            cmd = ["ffmpeg", "-i", str(video_path), "-ac", "1", "-ar", "8000", "-vn", "-f", "wav", "-y", temp_wav]
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)

            # 2. 读取音频并执行降采样
            audio = AudioSegment.from_wav(temp_wav)
            samples = np.array(audio.get_array_of_samples())

            chunk_size = 100  # 8000Hz 下每 100 个采样点取一极值
            total_samples = len(samples)
            pad_size = chunk_size - (total_samples % chunk_size)

            if pad_size != chunk_size:
                samples = np.append(samples, np.zeros(pad_size))

            # 矩阵化运算加速
            reshaped = samples.reshape(-1, chunk_size)
            peaks = np.abs(reshaped).max(axis=1)

            # 归一化并转为 Python List (Float)
            return np.round(peaks / 32768.0, 4).tolist()

        except subprocess.CalledProcessError as e:
            logger.error(f"Waveform FFmpeg Error: {e.stderr}")
            return []
        except Exception as e:
            logger.error(f"Waveform Calculation Error: {str(e)}")
            return []
        finally:
            # 物理清理
            if os.path.exists(temp_wav):
                os.remove(temp_wav)

    @staticmethod
    def _probe_file(file_path: str) -> Tuple[Dict, float]:
        """[镜像] 物理探测逻辑"""
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)

            duration = float(data.get("format", {}).get("duration", 0))
            tech_meta = {
                "container": data.get("format", {}).get("format_name"),
                "size": int(data.get("format", {}).get("size", 0)),
                "video": next(
                    (
                        {"codec": s.get("codec_name"), "width": s.get("width")}
                        for s in data.get("streams", [])
                        if s.get("codec_type") == "video"
                    ),
                    {},
                ),
            }
            return tech_meta, duration
        except Exception as e:
            raise RuntimeError(f"FFprobe extraction failed: {str(e)}")

    @staticmethod
    def _handle_failure(material_id: str, error: Exception):
        """[工业化补全] 错误持久化"""
        from apps.refinery.models import Material

        try:
            material = Material.objects.get(id=material_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            error_detail = f"[{timestamp}] Probe/Waveform Stage Failed: \n{str(error)}"

            logger.error(f"Refinement ERROR for {material_id}: {error_detail}")
            material.handle_failure(error_detail)
            material.save(update_fields=["status", "error_log", "modified"])
        except Exception:
            pass
