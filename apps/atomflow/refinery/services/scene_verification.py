# apps/atomflow/refinery/services/scene_verification.py

import logging
import os
import platform
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class SceneVerificationService:
    """
    [Refinery Operator] 场景切分验证服务 (本地调试用)。
    根据 Material.scenes 的时间戳，物理切分视频并烧录元数据字幕，用于人工核查切分准确性。
    """

    @staticmethod
    def run(video_path: Path, scenes: List[Dict[str, Any]], output_dir: Path) -> Dict[str, Any]:
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if not scenes:
            logger.warning("No scenes to verify.")
            return {"count": 0}

        output_dir.mkdir(parents=True, exist_ok=True)

        font_path = SceneVerificationService._get_font_path()
        logger.info(f"Using font: {font_path}")

        success_count = 0
        generated_files = []

        for scene in scenes:
            scene_id = scene.get("scene_id")
            start_time = scene.get("start_time")
            end_time = scene.get("end_time")
            content = scene.get("content", {})

            if start_time is None or end_time is None:
                continue

            duration = end_time - start_time
            if duration <= 0:
                continue

            output_filename = f"scene_{scene_id:03d}_subtitled.mp4"  # noqa：E231
            output_path = output_dir / output_filename

            subtitle_text = SceneVerificationService._format_content_for_subtitle(content)

            # Build FFmpeg command
            font_option = ""
            if font_path:
                # Escape for FFmpeg filter
                escaped_font_path = str(font_path).replace("\\", "/").replace(":", "\\:")
                font_option = f"fontfile='{escaped_font_path}':"  # noqa：E231

            video_filter = (
                f"drawtext=text='{subtitle_text}':{font_option}"  # noqa：E231
                f"fontsize=24:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:"  # noqa：E231
                f"box=1:boxcolor=black@0.6:boxborderw=10:line_spacing=5"  # noqa：E231
            )

            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(start_time),
                "-i",
                str(video_path),
                "-t",
                str(duration),
                "-vf",
                video_filter,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-c:a",
                "aac",
                "-avoid_negative_ts",
                "1",
                str(output_path),
            ]

            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                generated_files.append(str(output_path))
                success_count += 1
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to cut scene {scene_id}: {e.stderr.decode().strip()}")
            except Exception as e:
                logger.error(f"Unexpected error cutting scene {scene_id}: {e}")

        return {"count": success_count, "total": len(scenes), "output_dir": str(output_dir), "files": generated_files}

    @staticmethod
    def _format_content_for_subtitle(content_dict: Dict[str, Any]) -> str:
        parts = []
        main_keys = ["narrative_action", "location", "scene_type", "camera_logic", "character_dynamics", "reason"]
        for key in main_keys:
            val = content_dict.get(key)
            if val:
                # Handle LabelItem (dict) or str
                if isinstance(val, dict) and "label" in val:
                    parts.append(val["label"])
                else:
                    parts.append(str(val).strip())

        tags = content_dict.get("visual_mood_tags", [])
        if tags:
            tags_str = ", ".join(tags[:3])
            parts.append(f"Tags: {tags_str}")

        raw_text = " | ".join(parts)
        wrapped_lines = textwrap.wrap(raw_text, width=30)
        subtitle_text = "\n".join(wrapped_lines)

        # Escape for FFmpeg
        subtitle_text = subtitle_text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")
        return subtitle_text

    @staticmethod
    def _get_font_path() -> str:
        system = platform.system()
        if system == "Windows":
            candidates = [
                r"C:\Windows\fonts\msyh.ttc",  # 微软雅黑
                r"C:\Windows\fonts\simhei.ttf",  # 黑体
                r"C:\Windows\fonts\arial.ttf",
            ]
            for c in candidates:
                if os.path.exists(c):
                    return c
        elif system == "Linux":
            candidates = [
                # 优先查找中文字体 (需在 Dockerfile 中安装 fonts-wqy-zenhei 或 fonts-noto-cjk)
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/noto/NotoSansSC-Regular.otf",
                "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                # Fallback
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/noto/NotoSans-Regular.ttf",
            ]
            for c in candidates:
                if os.path.exists(c):
                    return c
        return ""
