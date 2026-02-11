import json
import subprocess
import sys
import textwrap
from pathlib import Path


def format_content_for_subtitle(content_dict):
    """
    将 content 字典格式化为单行字幕字符串。
    """
    parts = []

    # 1. 添加主要字段的 value
    main_keys = ["narrative_action", "location", "scene_type", "camera_logic", "character_dynamics", "reason"]
    for key in main_keys:
        if key in content_dict and content_dict[key]:
            parts.append(str(content_dict[key]).strip())

    # 2. 添加前三个 visual_mood_tags
    tags = content_dict.get("visual_mood_tags", [])
    if tags:
        tags_str = ", ".join(tags[:3])
        parts.append(f"Tags: {tags_str}")

    # 3. 用 | 分割所有部分
    raw_text = " | ".join(parts)

    # [New] 自动换行处理：每30个字符换一行，防止超出屏幕
    # [Fix] 针对竖屏视频，减少换行宽度
    wrapped_lines = textwrap.wrap(raw_text, width=30)
    subtitle_text = "\n".join(wrapped_lines)

    # 4. 为 ffmpeg drawtext 滤镜转义特殊字符
    # ' : \ -> \\, ' -> \', : -> \:, % -> \%
    subtitle_text = subtitle_text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")

    return subtitle_text


def verify_scene_cutting(video_path, json_path, output_dir):
    """
    独立验证脚本：根据 VSS Cloud 推理的 JSON 结果，使用 FFmpeg 对视频进行物理切片，
    并将场景的 content 内容作为字幕烧录到画面上。
    """
    video_path = Path(video_path)
    json_path = Path(json_path)
    output_dir = Path(output_dir)

    if not video_path.exists():
        print(f"❌ Error: Video file not found: {video_path}")
        return
    if not json_path.exists():
        print(f"❌ Error: JSON file not found: {json_path}")
        return

    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📂 Output directory: {output_dir}")

    # 读取 JSON
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error reading JSON: {e}")
        return

    scenes = data.get("scenes", [])
    if not scenes:
        print("⚠️ Warning: No scenes found in JSON.")
        return

    print(f"🎬 Found {len(scenes)} scenes to cut and burn subtitles.")
    print("-" * 60)

    success_count = 0

    for scene in scenes:
        scene_id = scene.get("scene_id")
        start_time = scene.get("start_time")
        end_time = scene.get("end_time")
        content = scene.get("content", {})

        # 参数校验
        if start_time is None or end_time is None:
            print(f"⚠️ Skipping Scene {scene_id}: Missing start/end time.")
            continue

        duration = end_time - start_time
        if duration <= 0:
            print(f"⚠️ Skipping Scene {scene_id}: Invalid duration ({duration}s).")
            continue

        output_filename = f"scene_{scene_id:03d}_subtitled.mp4"  # noqa E231
        output_path = output_dir / output_filename

        # 格式化字幕文本
        subtitle_text = format_content_for_subtitle(content)

        # 构建 FFmpeg 命令

        # [Fix] Windows 路径在 FFmpeg filter 中需要特殊转义
        # 1. 替换反斜杠; 2. 转义冒号 (C: -> C\:); 3. 补全 fontfile= 参数名和后续的冒号分隔符
        raw_font_path = r"C:\Windows\fonts\NotoSansSC-VF.ttf"
        escaped_font_path = raw_font_path.replace("\\", "/").replace(":", "\\:")
        font_option = f"fontfile='{escaped_font_path}':"  # noqa E231

        # [Fix] 针对竖屏视频调整字体大小和边距
        video_filter = f"drawtext=text='{subtitle_text}':{font_option}fontsize=24:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.6:boxborderw=10:line_spacing=5"  # noqa: E231,E501

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

        print(f"✂️ Processing Scene {scene_id} ({start_time}s - {end_time}s)...")

        try:
            # 执行命令
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            print(f"   ✅ Saved to: {output_filename}")
            success_count += 1
        except subprocess.CalledProcessError as e:
            print(f"   ❌ FFmpeg failed: {e.stderr.decode().strip()}")
        except Exception as e:
            print(f"   ❌ Unexpected error: {e}")

    print("-" * 60)
    print(f"🎉 Done! Successfully processed {success_count}/{len(scenes)} scenes.")


if __name__ == "__main__":
    # --- 在这里配置您的输入文件和输出目录 ---
    VIDEO_FILE = r"D:\DevProjects\PyCharmProjects\visify-ssw\media_root\source_files\5f593ac9-464e-472f-9d27-800eb9e86956\media\EP02.mp4"  # noqa E501
    JSON_FILE = r"D:\DevProjects\PyCharmProjects\visify-ssw\tests\testdata\slice_regrouper\3.json"
    OUTPUT_DIR = r"D:\DevProjects\PyCharmProjects\visify-ssw\tests\testdata\scenes_with_subtitles\version3"
    # -----------------------------------------

    # 检查占位符路径
    if "path/to/your" in VIDEO_FILE or "path/to/your" in JSON_FILE:
        print("✋ Please configure the VIDEO_FILE and JSON_FILE paths inside the script before running.")
        sys.exit(1)

    verify_scene_cutting(VIDEO_FILE, JSON_FILE, OUTPUT_DIR)
