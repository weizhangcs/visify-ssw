# tests/manual_cut_scenes.py
import json
import logging
import sys
from pathlib import Path

from tests.lib.video_tools import cut_scenes_from_video

# 配置路径
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))


# ================= 配置区 =================
# 1. 你的 JSON 结果文件路径 (请修改)
JSON_PATH = r"D:\DevProjects\PyCharmProjects\visify-ssw\tests\testdata\scene_annotation_result_232.json"

# 2. 对应的视频文件路径 (请修改)
VIDEO_PATH = r"D:\DevProjects\PyCharmProjects\visify-ssw\media_root\transcoding_outputs\c2c81885-7eb4-46f2-9c92-d2018be28b74\265\proxy.mp4"  # noqa:E501,E121

# 3. 输出目录
OUTPUT_DIR = Path(r"D:\DevProjects\PyCharmProjects\visify-ssw\tests\testdata\\cuts_verification")
# ==========================================

logging.basicConfig(level=logging.INFO)


def main():
    json_file = Path(JSON_PATH)
    video_file = Path(VIDEO_PATH)

    if not json_file.exists():
        print(f"❌ JSON file not found: {json_file}")
        return
    if not video_file.exists():
        print(f"❌ Video file not found: {video_file}")
        return

    print(f"🚀 Loading Result: {json_file.name}")
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load JSON: {e}")
        return

    # 解析 Cloud 返回的数据结构
    # Cloud 返回的通常包含 'scenes' 和 'slices' (或者 annotated_slices)
    scenes = data.get("scenes", [])

    # 尝试获取 slices，Cloud 返回的字段可能是 slices 或 annotated_slices
    slices = data.get("slices") or data.get("annotated_slices", [])

    if not scenes:
        print("⚠️ No 'scenes' found in JSON.")
        return

    if not slices:
        print("⚠️ No 'slices' found in JSON. Cannot map timestamps!")
        print("   (Did you download the full result file?)")
        return

    print(f"   Found {len(scenes)} scenes and {len(slices)} slices.")

    # 开始剪辑
    cut_scenes_from_video(video_file, scenes, slices, OUTPUT_DIR)


if __name__ == "__main__":
    main()
