# tests/manual_test_slicer.py
import json
import logging
from pathlib import Path

from apps.workflow.character_annotation.services.slice_extractor import SliceExtractorService

# 配置日志
logging.basicConfig(level=logging.INFO)

# --- 这里填入你本地真实存在的测试文件 ---
VIDEO_PATH = "../media_root/transcoding_outputs/62d8ebac-7443-4405-8fb2-e3aa198d5847/115/proxy.mp4"  # 你的 Proxy 视频
ASS_PATH = "../media_root/character_annotation/outputs/2025/12/23/001_ai.ass"  # Character Pre-Annotator 产出的 ASS
OUTPUT_DIR = Path("testdata/slicer_test_output")


def main():
    if not Path(VIDEO_PATH).exists() or not Path(ASS_PATH).exists():
        print("❌ 输入文件不存在，请修改脚本中的路径")
        return

    print("🚀 开始测试 Slicer...")

    # 实例化服务 (模拟 Worker-Media 环境)
    extractor = SliceExtractorService(output_root=OUTPUT_DIR, max_workers=8)

    # 运行
    result_slices = extractor.run(VIDEO_PATH, ASS_PATH)

    # 生成 JSON 用于检查
    json_path = OUTPUT_DIR / "milestone1_result.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result_slices, f, ensure_ascii=False, indent=2)

    print("\n✅ 测试完成！")
    print(f"1. 检查 JSON 结构: {json_path}")
    print(f"2. 检查图片质量: {OUTPUT_DIR}/frames/")

    # 简单断言
    if len(result_slices) > 0:
        first_slice = result_slices[0]
        print("\n🔍 抽查 Slice #1:")
        print(f"   - Type: {first_slice.get('type')}")  # noqa: E221
        print(f"   - Time: {first_slice.get('start_time')} - {first_slice.get('end_time')}")  # noqa: E221
        print(f"   - Frames: {len(first_slice.get('frames', []))} 张")  # noqa: E221
    else:
        print("⚠️ 警告: 没有生成任何 Slice，请检查 ASS 时间轴是否匹配视频")


if __name__ == "__main__":
    main()
