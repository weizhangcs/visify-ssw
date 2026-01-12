# apps/atomflow/refinery/services/audio_analyzer.py
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

# 这是一个重量级库，建议在 Dockerfile.media 中添加: pip install librosa
librosa: Any = None  # [Fix] Type hint as Any to suppress IDE warnings about None.load/pyin
try:
    import librosa
except ImportError:
    librosa = None

from apps.atomflow.refinery.schemas import AudioAnalysis, SubtitleItem  # noqa: E402

logger = logging.getLogger(__name__)


class AudioAnalyzerService:
    """
    [本地算子] 音频声学特征分析服务。

    职责：
    1. 从视频中加载音频。
    2. 针对对白轨道中的每一句，提取声学特征 (音高、语速、能量)。
    3. 基于特征进行简单的启发式判断 (性别、音高/语速/音量等级)。
    4. 将结果回填到 SubtitleItem 的 audio_analysis 字段。
    """

    @staticmethod
    def run(video_path: Path, dialogues: List[Dict], lang: str = "zh") -> List[Dict]:
        """
        执行音频分析任务。

        Args:
            video_path: 视频文件路径 (用于提取音频)。
            dialogues: 对白数据。
            lang: 语言代码 (zh/en)。

        Returns:
            更新后的对白数据 (带有 audio_analysis)。
        """
        if not dialogues:
            return []

        if librosa is None:
            logger.error("AudioAnalyzer: librosa not installed. Skipping analysis.")
            return dialogues

        logger.info(f"AudioAnalyzer: Loading audio from {video_path}...")

        # [Fix] 使用临时文件显式提取音频，避免 librosa 直接读取视频容器导致的 PySoundFile 警告和 audioread 废弃警告
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_wav_path = Path(tmp.name)

        try:
            # 1. 使用 FFmpeg 提取音频 (预处理：单声道 + 16kHz)
            cmd = [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(video_path),
                "-vn",  # 禁用视频流
                "-ac",
                "1",  # 单声道
                "-ar",
                "16000",  # 重采样至 16kHz
                "-f",
                "wav",
                str(temp_wav_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            # 2. 加载 WAV 文件 (此时 soundfile 后端可以完美处理)
            y, sr = librosa.load(str(temp_wav_path), sr=16000, mono=True)

        except subprocess.CalledProcessError as e:
            logger.error(f"AudioAnalyzer: FFmpeg extraction failed: {e.stderr.decode().strip()}")
            return dialogues
        except Exception as e:
            logger.error(f"AudioAnalyzer: Failed to load audio: {e}")
            return dialogues
        finally:
            if temp_wav_path.exists():
                temp_wav_path.unlink()

        updated_track = []

        for item_dict in dialogues:
            # 确保数据结构正确
            item = SubtitleItem(**item_dict)

            start_sample = int(item.start_time * sr)
            end_sample = int(item.end_time * sr)

            # 边界保护
            if start_sample >= len(y) or end_sample <= start_sample:
                updated_track.append(item.model_dump())
                continue

            # 2. 截取片段
            y_slice = y[start_sample:end_sample]
            duration = item.end_time - item.start_time

            # 3. 特征提取
            analysis = AudioAnalyzerService._analyze_segment(y_slice, sr, item.content, duration, lang)
            item.audio_analysis = analysis

            updated_track.append(item.model_dump())

        logger.info("AudioAnalyzer: Analysis complete.")
        return updated_track

    @staticmethod
    def _analyze_segment(y: np.ndarray, sr: int, text: str, duration: float, lang: str) -> AudioAnalysis:
        """
        [内部方法] 分析单个音频片段的声学特征。

        Args:
            y: 音频波形数据 (numpy array)。
            sr: 采样率。
            text: 对白文本内容。
            duration: 音频时长。
            lang: 语言代码。

        Returns:
            AudioAnalysis 对象。
        """
        # A. 音高 (Pitch) & 性别推断
        # 使用 PYIN 算法提取基频 (F0)
        f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=50, fmax=300, sr=sr)
        # 过滤掉无声片段 (NaN)
        valid_f0 = f0[~np.isnan(f0)]

        avg_pitch = 0.0
        gender = "Unknown"
        pitch_level = "Mid"

        if len(valid_f0) > 0:
            avg_pitch = float(np.mean(valid_f0))

            # 简单启发式规则 (Heuristic)
            # 男性通常 < 165Hz, 女性通常 > 165Hz
            if avg_pitch < 165:
                gender = "Male"
                pitch_level = "Low" if avg_pitch < 100 else "Mid"
            else:
                gender = "Female"
                pitch_level = "High" if avg_pitch > 220 else "Mid"

        # B. 语速 (Speed)
        speed_level = "Normal"
        chars_per_sec = 0.0

        if lang == "en":
            # 英文：基于单词数 (WPM/WPS) 判断等级
            # Normal: ~130-150 wpm (2.2-2.5 wps)
            # Fast: > 160 wpm (> 2.7 wps)
            # Slow: < 110 wpm (< 1.8 wps)
            words = text.split()
            wps = len(words) / duration if duration > 0 else 0

            if wps > 2.7:
                speed_level = "Fast"
            elif wps < 1.8:
                speed_level = "Slow"

            # 存储时仍计算 CPS (去除空格)，保持数据结构统一
            chars_per_sec = len(text.replace(" ", "")) / duration if duration > 0 else 0
        else:
            # 中文/默认：基于字符数 (CPS) 判断等级
            char_count = len(text.replace(" ", ""))
            chars_per_sec = char_count / duration if duration > 0 else 0
            if chars_per_sec > 5.0:
                speed_level = "Fast"
            elif chars_per_sec < 2.0:
                speed_level = "Slow"

        # C. 能量/响度 (Energy)
        rms = float(np.sqrt(np.mean(y**2)))
        volume_level = "Normal"
        if rms > 0.1:  # 经验值，需根据实际音频归一化情况调整
            volume_level = "Loud"
        elif rms < 0.02:
            volume_level = "Quiet"

        return AudioAnalysis(
            gender=gender,
            pitch_level=pitch_level,
            speed_level=speed_level,
            volume_level=volume_level,
            avg_pitch_hz=round(avg_pitch, 2),
            chars_per_sec=round(chars_per_sec, 2),
            rms_energy=round(rms, 4),
        )
