"""
使用说明 (Usage):
   docker compose -p vss-edge -f docker-compose.base.yml -f docker-compose.dev.yml
   run --rm worker-media python tests/atomflow/dubbing/test_script_refinement_service.py
   注意: 此测试需要网络连接以访问 VSS Cloud API。
"""
import json
import os
import sys
import time
from pathlib import Path

import django
import pandas as pd

# --- 1. 环境引导 (Bootstrap) ---
# 获取当前脚本所在目录，并向上寻找项目根目录，将其加入 sys.path
current_file = Path(__file__).resolve()

# 动态查找项目根目录 (向上寻找直到发现 'apps' 目录，兼容本地和 Docker 路径结构)
project_root = current_file.parent
while not (project_root / "apps").exists() and project_root != project_root.parent:
    project_root = project_root.parent

if str(project_root) not in sys.path:
    print(f"Adding project root to sys.path: {project_root}")
    sys.path.insert(0, str(project_root))

# --- 1.1 Django 环境初始化 (关键) ---
# 网络算子依赖 CloudApiService，需要读取 Django settings 中的 API 配置
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()

# --- 2. 导入服务 ---
try:
    from apps.atomflow.dubbing.services.script_refinement import ScriptRefinementService
except ImportError as e:
    print(f"[Error] Import failed: {e}")
    print("请确保项目根目录已正确添加到 PYTHONPATH。")
    sys.exit(1)


# --- 2.1 ASS 转换工具函数 ---
def format_ass_timestamp(seconds: float) -> str:
    """
    将秒数转换为 ASS 时间戳格式 (H:MM:SS.ss)
    例如: 6.4 -> 0:06:04.00 (注意：ASS 格式通常是 H:MM:SS.cc，其中 cc 是百分之一秒)
    """
    if seconds is None:
        seconds = 0.0

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))

    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"  # noqa: E231


ASS_HEADER_TEMPLATE = """[Script Info]
Title: Refined Script
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, \
StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,55,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,2,10,10,30,1
Style: Comment,Arial,35,&H80CCCCCC,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def convert_to_ass(json_data: dict, output_ass_path: Path):
    """
    将精修结果字典转换为 ASS 字幕文件
    """
    refined_script = json_data.get("refined_script", [])

    if not refined_script:
        print("Warning: No 'refined_script' found in JSON.")
        return

    ass_events = []
    dialogue_count = 0
    comment_count = 0

    for segment in refined_script:
        text = segment.get("refined_text")
        start_time = segment.get("start", 0.0)
        end_time = segment.get("end", 0.0)

        start_str = format_ass_timestamp(start_time)
        end_str = format_ass_timestamp(end_time)

        # 简单的逻辑判断：如果有 refined_text 且不是仅 OCR 忽略的噪音，则作为对白
        # 这里的判断逻辑可以根据实际业务需求调整
        if text and segment.get("source_of_truth") != "OCR_IGNORED":
            # Dialogue: 0,0:00:06.40,0:00:07.00,Default,,0,0,0,,快十二点了。
            event_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}"  # noqa: E231
            ass_events.append(event_line)
            dialogue_count += 1
        else:
            # 作为注释显示被忽略的内容或原始 OCR/ASR
            ignored_text = segment.get("original_ocr") or segment.get("original_asr") or "IGNORED"
            ignored_text = str(ignored_text).replace("\n", "\\N")
            event_line = f"Comment: 0,{start_str},{end_str},Comment,,0,0,0,,{ignored_text}"  # noqa: E231
            ass_events.append(event_line)
            comment_count += 1

    with open(output_ass_path, "w", encoding="utf-8-sig") as f:
        f.write(ASS_HEADER_TEMPLATE)
        f.write("\n".join(ass_events))

    print(f"ASS Conversion complete! Saved to: {output_ass_path}")
    print(f"  - Dialogues: {dialogue_count}")  # noqa: E221
    print(f"  - Comments:  {comment_count}")  # noqa: E221, E241


def main():
    print("=" * 50)
    print("   ScriptRefinementService Manual Test")
    print("=" * 50)

    # --- 3. 准备模拟输入数据 ---
    # 3.1 模拟 ASR 数据 (Perception Result)
    # 尝试从之前的测试结果加载，如果不存在则使用模拟数据
    perception_json_path = project_root / "tests/testdata/output/dubbing/perception_result.json"

    if perception_json_path.exists():
        print(f"[Info] Loading real ASR data from: {perception_json_path}")
        with open(perception_json_path, "r", encoding="utf-8") as f:
            perception_data = json.load(f)
    else:
        print("[Info] Real ASR data not found. Using mock data.")
        perception_data = {
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "你好，欢迎来到这个视频。", "confidence": 0.95},
                {"start": 2.6, "end": 5.0, "text": "今天我们将讨论人工智能。", "confidence": 0.88},
                {"start": 5.1, "end": 8.0, "text": "这是一个非常有趣的话题。", "confidence": 0.92},
            ]
        }

    # 3.2 模拟 OCR 数据 (LLM CSV)
    # 尝试从之前的测试结果加载，如果不存在则使用模拟数据
    ocr_csv_path = project_root / "media_root/dubbing/3d30b544-fd12-4f65-9000-3216b9984ad6/ocr_raw_for_llm.csv"

    if not ocr_csv_path.exists():
        print("[Info] Real OCR data not found. Creating mock CSV.")
        ocr_csv_path = project_root / "tests/testdata/output/dubbing/mock_ocr.csv"
        ocr_csv_path.parent.mkdir(parents=True, exist_ok=True)

        mock_ocr_data = [
            {"start_time": 0.5, "end_time": 2.0, "text": "欢迎观看", "avg_score": 0.98},
            {"start_time": 3.0, "end_time": 4.5, "text": "AI 讨论", "avg_score": 0.95},
        ]
        df = pd.DataFrame(mock_ocr_data)
        df.to_csv(ocr_csv_path, index=False)
    else:
        print(f"[Info] Loading real OCR data from: {ocr_csv_path}")

    # 输出路径
    output_base = project_root / "tests/testdata/output/dubbing"
    output_base.mkdir(parents=True, exist_ok=True)
    output_json_path = output_base / "script_refinement_result.json"

    print(f"ASR Segments: {len(perception_data.get('segments', []))}")
    print(f"OCR CSV: {ocr_csv_path}")
    print(f"Output JSON: {output_json_path}")

    # --- 4. 执行调用 ---
    try:
        print("\n>>> Starting Service Execution...")
        print("Note: This will call the VSS Cloud API. Please ensure your API Key is configured.")

        start_time = time.time()
        print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")

        # 直接调用静态方法 run
        # 假设目标语言为英语 (en)
        result = ScriptRefinementService.run(perception_data=perception_data, ocr_path=ocr_csv_path, lang="zh")

        end_time = time.time()
        duration = end_time - start_time

        print("\n>>> Execution Successful!")
        print(f"End Time:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")  # noqa: E241
        print(f"Duration:   {duration:.2f} seconds")  # noqa: E231,E241

        # --- 5. 保存并验证结果 ---
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Result saved to: {output_json_path}")

        refined_script = result.get("refined_script", [])
        print(f"\n[Verification] Received {len(refined_script)} refined segments.")

        if refined_script:
            print("\n--- First 3 Refined Segments Preview ---")
            for i, seg in enumerate(refined_script[:3]):
                print(f"[{i+1}] {seg.get('start', 0):.2f}s -> {seg.get('end', 0):.2f}s")  # noqa: E231,E226
                print(f"    Original: {seg.get('original_asr', '')}")
                print(f"    Refined:  {seg.get('refined_text', '')}")  # noqa: E241
                print(f"    Source:   {seg.get('source_of_truth', 'N/A')}")  # noqa: E241

        # --- 6. 后处理：生成 ASS 字幕 ---
        output_ass_path = output_base / "script_refinement_result.ass"
        convert_to_ass(result, output_ass_path)

    except Exception as e:
        print(f"\n[Execution Failed] {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
