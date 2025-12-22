import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def generate_peaks_from_video(video_path, output_json_path, num_points=2000):
    try:
        import numpy as np
        from pydub import AudioSegment
    except ImportError:
        logger.error("NumPy or PyDub not installed. Waveform generation skipped.")
        return False

    """
    从视频生成波形峰值数据 (JSON)。

    流程:
    1. FFmpeg: 视频 -> 8000Hz 单声道 WAV (临时文件)
    2. Pydub/Numpy: 读取 WAV -> 重采样/取最大值 -> 归一化 -> 列表
    3. Save: 存为 JSON
    """

    temp_wav = str(output_json_path).replace(".json", ".wav")

    try:
        # 1. 使用 FFmpeg 提取极低质量音频 (为了速度)
        # -ac 1: 单声道
        # -ar 8000: 8kHz 采样率 (画波形足够了)
        cmd = ["ffmpeg", "-i", str(video_path), "-ac", "1", "-ar", "8000", "-vn", "-f", "wav", "-y", temp_wav]  # 去除视频流

        # 此时只需快速提取，不需要高质量
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 2. 使用 Pydub + Numpy 计算峰值
        if not os.path.exists(temp_wav):
            raise FileNotFoundError("Audio extraction failed")

        # 加载音频 (Pydub lazy loading, 但这里我们已经转成了 wav，所以很快)
        audio = AudioSegment.from_wav(temp_wav)

        # 转为 numpy 数组 (int16)
        samples = np.array(audio.get_array_of_samples())

        # 3. 下采样 (Downsampling)
        # 我们不需要每一个采样点，只需要提取特征点（峰值）
        # 目标：生成足够前端渲染的数据量。
        # 假设前端每秒渲染 20-100 个像素，对于长视频，我们可能需要几万个点。
        # 这里采用“固定步长”采样，或者“分桶取最大值”。

        total_samples = len(samples)

        # 策略：每 N 个采样点取一个绝对值的最大值
        # 8000Hz 下，每 80 个点对应 0.01秒。
        # 我们每 100 个点取一个极值，相当于 80Hz 的精度，足够精细
        chunk_size = 100

        # Pad array to be divisible by chunk_size
        pad_size = chunk_size - (total_samples % chunk_size)
        if pad_size != chunk_size:
            samples = np.append(samples, np.zeros(pad_size))

        # Reshape into chunks
        reshaped = samples.reshape(-1, chunk_size)

        # 计算每个 chunk 的最大绝对值
        # np.abs(reshaped).max(axis=1) 比循环快得多
        peaks = np.abs(reshaped).max(axis=1)

        # 4. 归一化 (0.0 - 1.0)
        # 16-bit audio max value is 32768
        normalized_peaks = np.round(peaks / 32768.0, 4)  # 保留4位小数

        # 转换为列表
        peaks_list = normalized_peaks.tolist()

        # 5. 写入 JSON
        data = {
            "version": 1,
            "sample_rate": 8000,
            "samples_per_pixel": chunk_size,
            "length": len(peaks_list),
            "data": peaks_list,
        }

        with open(output_json_path, "w") as f:
            json.dump(data, f)

        return True

    except Exception as e:
        print(f"Error generating waveform: {e}")
        return False

    finally:
        # 清理临时 WAV
        if os.path.exists(temp_wav):
            os.remove(temp_wav)
