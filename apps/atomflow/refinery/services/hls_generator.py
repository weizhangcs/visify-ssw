# apps/atomflow/refinery/services/hls_generator.py
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class HLSService:
    @staticmethod
    def run(input_path: Path, output_dir: Path):
        """
        [物理算子] FFmpeg HLS 标准切片
        职责：物理切片 + 目录保护 + 详尽错误捕获
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
            "copy",
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
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)  # noqa: F841
            logger.info(f"Refinery HLS Success: {index_path.name}")
            return index_path

        except subprocess.CalledProcessError as e:
            error_detail = e.stderr if e.stderr else "Unknown HLS Error"
            logger.error(f"FFmpeg HLS FAILED: {error_detail}")
            raise RuntimeError(f"HLS Physical Error: {error_detail}")
        except Exception as e:
            logger.error(f"HLS unexpected error: {str(e)}")
            raise
