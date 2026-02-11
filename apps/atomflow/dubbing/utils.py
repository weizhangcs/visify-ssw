import gc
import json
import logging
import subprocess

import numpy as np
import torch

logger = logging.getLogger(__name__)


def load_audio_ffmpeg(audio_path: str, sr: int) -> np.ndarray:
    """
    使用 FFmpeg (subprocess) 加载、解码和重采样音频，性能远高于 librosa。
    """
    cmd = [
        "ffmpeg",
        "-i",
        audio_path,
        "-f",
        "s16le",  # format: signed 16-bit little-endian
        "-acodec",
        "pcm_s16le",  # audio codec
        "-ac",
        "1",  # audio channels: 1 (mono)
        "-ar",
        str(sr),  # audio sample rate
        "-",  # output to stdout
    ]
    try:
        # check=True 会在 ffmpeg 返回非零退出码时自动抛出 CalledProcessError
        res = subprocess.run(cmd, capture_output=True, check=True)
        # 将 ffmpeg 输出的原始 PCM 字节流转换为 NumPy 浮点数组，并归一化到 [-1.0, 1.0]
        wav = np.frombuffer(res.stdout, np.int16).flatten().astype(np.float32) / 32768.0
        return wav
    except subprocess.CalledProcessError as e:
        # 将 ffmpeg 的错误输出打印到日志，方便调试
        logger.error(f"FFmpeg failed to process {audio_path}. Return code: {e.returncode}")
        logger.error(f"FFmpeg stderr: {e.stderr.decode(errors='ignore')}")
        raise IOError(f"FFmpeg processing failed for {audio_path}") from e
    except FileNotFoundError:
        logger.error("FFmpeg command not found. Please ensure FFmpeg is installed and in your system's PATH.")
        raise


def cleanup_gpu():
    """清理 GPU 显存"""
    print("   🧹 Cleaning up GPU resources...")
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def format_timestamp(seconds):
    whole_seconds = int(seconds)
    milliseconds = int((seconds - whole_seconds) * 1000)
    hours = whole_seconds // 3600
    minutes = (whole_seconds % 3600) // 60
    seconds = whole_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"  # noqa: E231


class FFmpegVideoReader:
    def __init__(self, path):
        self.path = str(path)
        self.width, self.height, self.fps, self.total_frames = self._get_metadata()
        self.frame_len = self.width * self.height * 3
        self.process = self._start_ffmpeg()

    def _get_metadata(self):
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,nb_frames",
            "-of",
            "json",
            self.path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        info = json.loads(res.stdout)["streams"][0]
        w = int(info["width"])
        h = int(info["height"])
        fps_str = info["r_frame_rate"]
        num, den = map(int, fps_str.split("/"))
        fps = num / den
        frames = int(info.get("nb_frames", 0))
        return w, h, fps, frames

    def _start_ffmpeg(self):
        cmd = [
            "ffmpeg",
            "-hwaccel",
            "cuda",
            "-i",
            self.path,
            "-f",
            "image2pipe",
            "-pix_fmt",
            "bgr24",
            "-vcodec",
            "rawvideo",
            "-",
        ]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**7)

    def read(self):
        raw = self.process.stdout.read(self.frame_len)
        if len(raw) != self.frame_len:
            return False, None
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((self.height, self.width, 3))
        return True, frame

    def release(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
