# apps/atomflow/refinery/services/hls_generator.py
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class HLSGeneratorService:
    """
    [物理算子] HLS 切片生成服务。

    职责：
    1. 使用 FFmpeg 将视频文件切片为 HLS (m3u8 + ts)。
    2. 确保输出目录存在。
    3. 捕获并处理 FFmpeg 执行错误。
    """

    @staticmethod
    def run(input_path: Path, output_dir: Path) -> Path:
        """
        执行 HLS 切片任务。

        Args:
            input_path: 输入视频路径。
            output_dir: 输出目录路径。

        Returns:
            生成的 index.m3u8 文件的绝对路径。

        Raises:
            FileNotFoundError: 如果输入文件不存在。
            RuntimeError: 如果 FFmpeg 执行失败。
        """
        if not input_path.exists():
            raise FileNotFoundError(f"HLS Input Missing: {input_path}")

        output_dir.mkdir(parents=True, exist_ok=True)
        index_path = output_dir / "index.m3u8"

        cmd = [
            "ffmpeg",
            "-i",
            str(input_path),
            "-c",
            "copy",  # 直接复制流，不重编码 (假设输入已经是 Proxy)
            "-f",
            "hls",
            "-hls_time",
            "10",
            "-hls_list_size",
            "0",
            "-y",
            str(index_path),
        ]

        logger.info(f"Refinery HLS Start: {input_path.name}")

        try:
            # capture_output=True 捕获 stdout/stderr
            # check=True 如果 ffmpeg 退出码不为 0 则抛出异常
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"Refinery HLS Success: {index_path.name}")
            return index_path

        except subprocess.CalledProcessError as e:
            error_detail = e.stderr if e.stderr else "Unknown HLS Error"
            logger.error(f"FFmpeg HLS FAILED: {error_detail}")
            raise RuntimeError(f"HLS Physical Error: {error_detail}")
        except Exception as e:
            logger.error(f"HLS unexpected error: {str(e)}")
            raise
