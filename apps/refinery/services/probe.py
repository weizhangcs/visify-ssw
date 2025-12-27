# 文件路径: apps/refinery/services/probe.py

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class ProbeService:
    @staticmethod
    def run(proxy_path: Path, temp_wav_path: Path) -> Tuple[Dict, float, List[float]]:
        """
        [物理算子] 针对已生成的 Proxy 进行探测
        输入：
            proxy_path: 代理视频的绝对路径 (Path)
            temp_wav_path: 由 Context 提供的隔离临时音频文件路径 (Path)
        输出：
            (元数据字典, 时长, 声纹数据列表)
        """
        # 1. 探测 Proxy 的物理时长和技术参数
        tech_meta, duration = ProbeService._probe_file(proxy_path)

        # 2. 针对 Proxy 计算声纹，使用 Context 提供的临时路径
        waveform_list = ProbeService._generate_peaks_in_memory(proxy_path, temp_wav_path)

        return tech_meta, duration, waveform_list

    @staticmethod
    def _probe_file(file_path: Path) -> Tuple[Dict, float]:
        """[物理镜像] ffprobe 提取逻辑"""
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(file_path)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)

            duration = float(data.get("format", {}).get("duration", 0))
            tech_meta = {
                "container": data.get("format", {}).get("format_name"),
                "size": int(data.get("format", {}).get("size", 0)),
                "video": next(
                    (
                        {"codec": s.get("codec_name"), "width": s.get("width"), "height": s.get("height")}
                        for s in data.get("streams", [])
                        if s.get("codec_type") == "video"
                    ),
                    {},
                ),
            }
            return tech_meta, duration
        except Exception as e:
            raise RuntimeError(f"FFprobe extraction failed for {file_path}: {str(e)}")

    @staticmethod
    def _generate_peaks_in_memory(video_path: Path, temp_wav: Path) -> List[float]:
        """
        [物理镜像] 核心声纹采样算法
        不再自行创建 temp 文件，而是直接使用传入的 temp_wav 路径
        """
        try:
            import numpy as np
            from pydub import AudioSegment
        except ImportError:
            logger.error("Dependency missing: numpy or pydub not found.")
            return []

        try:
            # 1. 提取音频流到指定临时路径
            cmd = ["ffmpeg", "-i", str(video_path), "-ac", "1", "-ar", "8000", "-vn", "-f", "wav", "-y", str(temp_wav)]
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)

            # 2. 读取音频并执行降采样
            audio = AudioSegment.from_wav(str(temp_wav))
            samples = np.array(audio.get_array_of_samples())

            chunk_size = 100
            total_samples = len(samples)
            pad_size = chunk_size - (total_samples % chunk_size)

            if pad_size != chunk_size:
                samples = np.append(samples, np.zeros(pad_size))

            # 矩阵化运算加速
            reshaped = samples.reshape(-1, chunk_size)
            peaks = np.abs(reshaped).max(axis=1)

            # 归一化并转为 Python List (Float)
            return np.round(peaks / 32768.0, 4).tolist()

        except Exception as e:
            logger.error(f"Waveform Calculation Error: {str(e)}")
            return []
