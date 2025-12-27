# 文件路径: apps/refinery/services/transcoder.py

import json
import logging
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction

# 获取模块级标准日志记录器
logger = logging.getLogger(__name__)


class TranscodeService:
    @staticmethod
    def execute_and_report(material_id: str):
        """
        [原子服务] 物理转码镜像 (工业化增强型)
        职责：Source -> Proxy MP4，并严格按照 CharField 路径规范记录产出。
        """
        from apps.refinery.models import Material

        with transaction.atomic():
            # 使用锁定机制确保 FSM 状态一致性
            material = Material.objects.select_for_update().get(id=material_id)
            media = material.media

            if not media.source_video:
                raise ValueError(f"Material {material_id} 缺失源视频物理路径")

            source_abs_path = Path(media.source_video.path)

            # 1. 准备物理产出目录：refinery/proxy/{uuid}/
            rel_proxy_dir = Path("refinery") / "proxy" / str(material_id)
            abs_proxy_dir = Path(settings.MEDIA_ROOT) / rel_proxy_dir

            # 清理旧数据，确保原子性
            if abs_proxy_dir.exists():
                shutil.rmtree(abs_proxy_dir)
            abs_proxy_dir.mkdir(parents=True, exist_ok=True)

            proxy_filename = "proxy.mp4"
            abs_proxy_path = abs_proxy_dir / proxy_filename
            rel_proxy_path = rel_proxy_dir / proxy_filename

            # 2. 准备工作临时目录（FFmpeg 中间过程）
            work_dir = Path(settings.MEDIA_ROOT) / "temp_refinery_trans" / str(material_id)
            work_dir.mkdir(parents=True, exist_ok=True)
            temp_mp4_path = work_dir / "temp_proxy.mp4"

            try:
                logger.info(f"Refinement Started: Processing video '{source_abs_path.name}' for Material {material_id}")

                # --- 物理镜像执行 (FFmpeg 转码) ---
                cmd_proxy = [
                    "ffmpeg",
                    "-i",
                    str(source_abs_path),
                    "-c:v",
                    "libx264",
                    "-b:v",
                    "1M",
                    "-vf",
                    "scale=-2:720",
                    "-preset",
                    "ultrafast",
                    "-y",
                    str(temp_mp4_path),
                ]

                # 执行并捕获 stderr 用于异常分析
                result = subprocess.run(cmd_proxy, check=True, capture_output=True, text=True)
                logger.debug(f"FFmpeg output for {material_id}: {result.stdout}")

                # 3. 提取时长与技术校验
                probe_cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(temp_mp4_path)]
                probe_res = subprocess.check_output(probe_cmd)
                meta = json.loads(probe_res)
                material.duration = float(meta["format"]["duration"])

                # 4. 产出物持久化：从 Temp 搬运到正式目录
                shutil.move(str(temp_mp4_path), str(abs_proxy_path))

                # 记录相对路径字符串 (CharField)
                material.proxy_video = str(rel_proxy_path).replace("\\", "/")

                # 5. 范式回归：跳转回 PENDING 决策位
                if material.status == material.Status.TRANSCODING:
                    material.finish_current_task()

                # 成功后确保清除旧的错误日志
                material.error_log = ""
                material.save(update_fields=["proxy_video", "duration", "status", "error_log", "modified"])

                logger.info(f"Refinement Successful: Material {material_id} proxy is ready at {material.proxy_video}")

            except subprocess.CalledProcessError as e:
                error_detail = f"FFmpeg Process Error (Return Code: {e.returncode})\n" f"--- STDERR ---\n{e.stderr}\n"
                TranscodeService._handle_service_failure(material, "Physical Transcoding", error_detail)
                raise
            except Exception as e:
                error_detail = f"System Exception: {str(e)}\n{traceback.format_exc()}"
                TranscodeService._handle_service_failure(material, "Service Logic", error_detail)
                raise
            finally:
                if work_dir.exists():
                    shutil.rmtree(work_dir)

    @staticmethod
    def _handle_service_failure(material, stage, detail):
        """[内部审计] 统一处理精炼失败"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_error = f"[{timestamp}] Stage: {stage}\n{detail}"
        logger.error(f"Refinement FAILED for Material {material.id} at stage '{stage}': \n{detail}")
        material.handle_failure(formatted_error)
        material.save(update_fields=["status", "error_log", "modified"])
