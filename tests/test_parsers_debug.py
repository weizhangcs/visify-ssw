import json
import os
import sys
from pathlib import Path

import django

# ==============================================================================
# 1. 环境初始化
# ==============================================================================
# 定位项目根目录 (假设脚本在 tests/ 目录下)
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# [修正] 指定正确的 Settings 路径
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()

# 引入解析器 (此时 Django 环境已就绪)
from apps.workflow.annotation.services.parsers import parse_ass_content, parse_scene_json_content  # noqa E402


# ==============================================================================
# 2. 执行测试
# ==============================================================================
def run_real_data_test():
    print("=" * 60)
    print("Testing Parsers with REAL Data")
    print("=" * 60)

    # --- 定义文件路径 ---
    ass_path = BASE_DIR / "media_root/character_annotation/outputs/2025/12/23/EP02_ai.ass"
    json_path = BASE_DIR / "tests/testdata/scene_annotation_result_232.json"

    # --- A. 测试 ASS 字幕解析 ---
    if not ass_path.exists():
        print(f"[Error] ASS file not found: {ass_path}")
    else:
        print(f"\n[Step 1] Reading ASS file: {ass_path.name} ...")
        try:
            with open(ass_path, "r", encoding="utf-8") as f:
                ass_content = f.read()

            dialogues = parse_ass_content(ass_content)
            print(f"-> Successfully parsed {len(dialogues)} dialogue items.")

            # 抽样打印前3条，验证清洗效果
            for i, item in enumerate(dialogues[:3]):
                print(
                    f"   [{i}] {item.start:.2f}-{item.end:.2f} | {item.content.speaker}: {item.content.text[:50]}..."  # noqa E231
                )

        except Exception as e:
            print(f"-> FAILED parsing ASS: {e}")

    # --- B. 测试 Scene JSON 解析 ---
    if not json_path.exists():
        print(f"\n[Error] JSON file not found: {json_path}")
    else:
        print(f"\n[Step 2] Reading Scene JSON file: {json_path.name} ...")
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                # 这里读取为字符串传给 parser (模拟从数据库或文件读取原始内容)
                json_content_str = f.read()

            scenes = parse_scene_json_content(json_content_str)
            print(f"-> Successfully parsed {len(scenes)} scene items.")

            # 抽样打印前3条，验证映射逻辑
            for i, item in enumerate(scenes[:3]):
                print(f"   [{i}] Time: {item.start:.2f}-{item.end:.2f}")  # noqa E231
                print(f"       Label: {item.content.label}")  # noqa E241
                print(f"       Type:  {item.content.scene_type}")  # noqa E241
                print(f"       Tags:  {item.content.tags}")  # noqa E241
                print(f"       Logic: {item.content.camera_logic}")  # noqa E241
                print("-" * 40)

            # --- C. 导出完整结果 (可选，方便查看) ---
            output_file = BASE_DIR / "tests/debug_parser_output.json"
            final_output = {
                "dialogues": [d.model_dump() for d in dialogues] if "dialogues" in locals() else [],
                "scenes": [s.model_dump() for s in scenes] if "scenes" in locals() else [],
            }
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(final_output, f, indent=2, ensure_ascii=False)
            print(f"\n[Success] Full parsed result saved to: {output_file}")

        except Exception as e:
            print(f"-> FAILED parsing JSON: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    run_real_data_test()
