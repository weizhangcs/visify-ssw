# 文件路径: apps/refinery/services/probe.py

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class ProbeService:
    @staticmethod
    def execute_and_report(material_id: str):
        """
        :param material_id:
        [原子服务] 媒体物理探测
        职责：通过 ffprobe 获取视频流的技术元数据。
        """
        from apps.refinery.models import Material

        material = Material.objects.get(id=material_id)

        # 执行物理探测逻辑
        tech_meta, duration = ProbeService._probe_file(material.media.source_video.path)

        # 写入物理数据
        material.tech_meta = tech_meta
        material.duration = duration
        print(f"DEBUG: ProbeService saving data for {material_id}")  # 确认 Service 是否走到了这一步
        material.save(update_fields=["tech_meta", "duration", "modified"])
        print("DEBUG: ProbeService save completed")

        # 【核心修正】显式结束当前任务，将状态由 PROBING 变为 PENDING
        if material.status == material.Status.PROBING:
            material.finish_current_task()
        # 【关键】一次性保存所有变更，必须包含 status
        print(f"DEBUG: Saving tech_meta and returning to PENDING for {material_id}")
        material.save(update_fields=["tech_meta", "duration", "status", "modified"])

        # 同步更新 Media TODO: 利旧兼容目的，重构后要删除。
        material.media.duration = duration
        material.media.save(update_fields=["duration"])

    @staticmethod
    def _probe_file(file_path: str) -> Tuple[Dict, float]:
        """
        执行探测并返回元数据字典和总时长。
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Probe target not found: {file_path}")

        # 构建 ffprobe 命令
        # -show_format: 获取容器级别元数据
        # -show_streams: 获取流级别元数据 (视频/音频)
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")
            data = json.loads(result.stdout)

            # 提取时长 (优先从 format 提取，其次从第一条流提取)
            duration_str = data.get("format", {}).get("duration", 0)
            if not duration_str and data.get("streams"):
                duration_str = data["streams"][0].get("duration", 0)

            duration = float(duration_str)

            # 提取并简化技术标签 (供后期决策用)
            tech_meta = {
                "container": data.get("format", {}).get("format_name"),
                "size": int(data.get("format", {}).get("size", 0)),
                "bit_rate": int(data.get("format", {}).get("bit_rate", 0)),
                "video": {},
                "audio": {},
            }

            for stream in data.get("streams", []):
                s_type = stream.get("codec_type")
                if s_type == "video" and not tech_meta["video"]:
                    tech_meta["video"] = {
                        "codec": stream.get("codec_name"),
                        "width": stream.get("width"),
                        "height": stream.get("height"),
                        "fps": stream.get("r_frame_rate"),
                        "pix_fmt": stream.get("pix_fmt"),
                    }
                elif s_type == "audio" and not tech_meta["audio"]:
                    tech_meta["audio"] = {
                        "codec": stream.get("codec_name"),
                        "channels": stream.get("channels"),
                        "sample_rate": stream.get("sample_rate"),
                    }

            return tech_meta, duration

        except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"FFprobe failed for {file_path}: {str(e)}")
            raise RuntimeError(f"FFprobe extraction failed: {str(e)}")
