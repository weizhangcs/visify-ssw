# 文件路径: apps/atomflow/refinery/services/probe.py

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from ..schemas import TechMeta, VideoStreamMeta

logger = logging.getLogger(__name__)


class ProbeService:
    """
    [物理算子] 媒体文件探测服务。

    职责：
    1. 使用 FFprobe 提取视频文件的技术元数据 (TechMeta)。
    2. 使用 FFmpeg 和 NumPy 计算音频波形数据 (Waveform)。
    """

    @staticmethod
    def run(proxy_path: Path, temp_wav_path: Path) -> Tuple[Dict, float, List[float]]:
        """
        执行探测任务。

        Args:
            proxy_path: 代理视频的绝对路径。
            temp_wav_path: 用于生成波形的临时 WAV 文件路径。

        Returns:
            一个元组，包含：
            - tech_meta (Dict): 技术元数据字典。
            - duration (float): 视频时长（秒）。
            - waveform_list (List[float]): 归一化的波形数据列表。
        """
        # 1. 探测 Proxy 的物理时长和技术参数
        tech_meta, duration = ProbeService._probe_file(proxy_path)

        # 2. 针对 Proxy 计算声纹，使用 Context 提供的临时路径
        waveform_list = ProbeService._generate_peaks_in_memory(proxy_path, temp_wav_path)

        return tech_meta, duration, waveform_list

    @staticmethod
    def _probe_file(file_path: Path) -> Tuple[Dict, float]:
        """
        [内部方法] 调用 ffprobe 提取元数据。

        Args:
            file_path: 目标文件路径。

        Returns:
            (TechMeta Dict, Duration Float)

        Raises:
            RuntimeError: 如果 ffprobe 执行失败。
        """
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(file_path)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            data = json.loads(result.stdout)

            duration = float(data.get("format", {}).get("duration", 0))

            video_stream_data = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})

            tech_meta = TechMeta(
                container=data.get("format", {}).get("format_name"),
                size=int(data.get("format", {}).get("size", 0)),
                video=VideoStreamMeta(
                    codec=video_stream_data.get("codec_name"),
                    width=video_stream_data.get("width"),
                    height=video_stream_data.get("height"),
                ),
            )
            return tech_meta.model_dump(), duration
        except Exception as e:
            raise RuntimeError(f"FFprobe extraction failed for {file_path}: {str(e)}")

    @staticmethod
    def _generate_peaks_in_memory(video_path: Path, temp_wav: Path) -> List[float]:
        """
        [内部方法] 计算音频波形数据。

        流程：
        1. 使用 ffmpeg 从视频中提取音频流到临时 WAV 文件。
        2. 使用 pydub 读取 WAV 文件。
        3. 使用 numpy 进行降采样和归一化处理。

        Args:
            video_path: 源视频路径。
            temp_wav: 临时 WAV 输出路径。

        Returns:
            归一化的波形峰值列表 (0.0 - 1.0)。
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
