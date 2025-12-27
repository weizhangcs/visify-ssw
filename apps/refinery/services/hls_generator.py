# 文件路径: apps/refinery/services/hls_generator.py

import logging
import shutil
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


class HLSService:
    @staticmethod
    def execute_and_report(material_id: str):
        """
        [原子服务] 流媒体切片生产
        职责：基于精炼后的 Proxy 视频生成 HLS 切片，并记录物理索引路径。
        输入依赖：material.proxy_video (FileField 物理路径)
        """
        from apps.refinery.models import Material

        try:
            with transaction.atomic():
                # 锁定行，确保 FSM 环境安全
                material = Material.objects.select_for_update().get(id=material_id)

                # 严格校验：必须基于已精炼的 Proxy 视频
                if not material.proxy_video:
                    raise ValueError(f"HLS Refinement Failed: Material {material_id} 缺失 Proxy 视频。")

                proxy_abs_path = Path(settings.MEDIA_ROOT) / Path(material.proxy_video)
                if not proxy_abs_path.exists():
                    raise FileNotFoundError(f"Proxy 物理文件未找到: {proxy_abs_path}")

                # 准备物理产出目录：refinery/hls/{uuid}/
                rel_output_dir = Path("refinery") / "hls" / str(material_id)
                abs_output_dir = Path(settings.MEDIA_ROOT) / rel_output_dir

                # 清理旧的切片，确保原子生产的一致性
                if abs_output_dir.exists():
                    shutil.rmtree(abs_output_dir)
                abs_output_dir.mkdir(parents=True, exist_ok=True)

                hls_index_filename = "index.m3u8"
                abs_index_path = abs_output_dir / hls_index_filename
                rel_index_path = rel_output_dir / hls_index_filename

                # --- 物理镜像执行 (FFmpeg Fast Slice) ---
                # 使用 -c copy 确保极速切片，且不改变画质
                logger.info(f"HLS Fragmenting: Starting for {material_id} using Proxy.")
                cmd_hls = [
                    "ffmpeg",
                    "-i",
                    str(proxy_abs_path),
                    "-c",
                    "copy",
                    "-f",
                    "hls",
                    "-hls_time",
                    "10",
                    "-hls_list_size",
                    "0",
                    "-y",
                    str(abs_index_path),
                ]

                subprocess.run(cmd_hls, check=True, capture_output=True, text=True)

                # --- 数据落地 ---
                # 仅保存字符串路径，不再使用 FileField 保存对象
                material.hls_playlist = str(rel_index_path).replace("\\", "/")

                # --- 范式回归 ---
                if material.status == material.Status.HLS_FRAGMENTING:
                    material.finish_current_task()

                material.error_log = ""  # 成功清除旧日志
                material.save(update_fields=["hls_playlist", "status", "error_log", "modified"])

                logger.info(f"HLS Refinement Successful: Index saved at {material.hls_playlist}")

        except subprocess.CalledProcessError as e:
            HLSService._handle_failure(material_id, f"FFmpeg Slicing Error: \n{e.stderr}")
            raise
        except Exception as e:
            HLSService._handle_failure(material_id, f"Service Exception: {str(e)}\n{traceback.format_exc()}")
            raise

    @staticmethod
    def _handle_failure(material_id: str, error_detail: str):
        """工业化异常记录"""
        from apps.refinery.models import Material

        try:
            material = Material.objects.get(id=material_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted_error = f"[{timestamp}] HLS Stage Failed: \n{error_detail}"

            logger.error(f"HLS Error for {material_id}: {formatted_error}")
            material.handle_failure(formatted_error)
            material.save(update_fields=["status", "error_log", "modified"])
        except Exception:
            pass
