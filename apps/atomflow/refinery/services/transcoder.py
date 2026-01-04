# apps/atomflow/refinery/services/transcoder.py
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class TranscodeService:
    """
    [物理算子] 视频转码服务。

    职责：
    1. 使用 FFmpeg 将源视频转码为标准化的代理视频 (720p, H.264)。
    2. 提供详细的日志监控和错误捕获。
    """

    @staticmethod
    def run(source_path: Path, output_path: Path) -> bool:
        """
        执行视频转码任务。

        Args:
            source_path: 源视频文件的绝对路径。
            output_path: 转码后输出文件的绝对路径。

        Returns:
            True 如果转码成功。

        Raises:
            RuntimeError: 如果 FFmpeg 执行失败。
        """
        cmd = [
            "ffmpeg",
            "-i",
            str(source_path),
            "-c:v",
            "libx264",
            "-b:v",
            "1M",
            "-vf",
            "scale=-2:720",
            "-preset",
            "ultrafast",
            "-y",
            str(output_path),
        ]

        logger.info(f"Refinery Transcode Start: {source_path.name}")

        try:
            # capture_output=True 捕获 stdout/stderr
            # check=True 如果 ffmpeg 退出码不为 0 则抛出异常
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"Refinery Transcode Success: {output_path.name}")
            return True

        except subprocess.CalledProcessError as e:
            # 捕获 FFmpeg 的具体报错信息
            error_detail = e.stderr if e.stderr else "Unknown FFmpeg Error"
            logger.error(f"FFmpeg Transcode FAILED for {source_path.name}: {error_detail}")
            # 重新抛出，携带物理层的报错详情，供 Task 捕获
            raise RuntimeError(f"FFmpeg Physical Error: {error_detail}")
        except Exception as e:
            logger.error(f"Transcode unexpected error: {str(e)}")
            raise
