import os
import sys
import time
from pathlib import Path

import django

# 1. 环境初始化
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()

from django.conf import settings  # noqa: E402

from apps.atomflow.refinery.models import Material  # noqa: E402
from apps.atomflow.refinery.services.audio_analyzer import AudioAnalyzerService  # noqa: E402


def run_test():
    material_id = "aab9252f-ba90-4762-8537-2b79a0cb38fb"
    print("=" * 60)
    print(f"🚀 AudioAnalyzer 本地验证 | Material: {material_id}")
    print("=" * 60)

    # 1. 获取数据
    try:
        material = Material.objects.get(id=material_id)
    except Material.DoesNotExist:
        print(f"❌ 错误: 找不到 Material {material_id}")
        return

    if not material.proxy_video:
        print("❌ 错误: Material 缺少 proxy_video")
        return

    if not material.dialogue:
        print("❌ 错误: Material 缺少 dialogue")
        return

    # 构造视频绝对路径
    video_path = Path(settings.MEDIA_ROOT) / material.proxy_video
    if not video_path.exists():
        print(f"❌ 错误: 视频文件不存在: {video_path}")
        return

    print(f"✅ 视频路径: {video_path}")
    print(f"✅ 对白条目数: {len(material.dialogue)}")

    # 2. 执行算子
    print("\n🎧 正在执行 AudioAnalyzerService (Librosa)...")
    start_ts = time.time()

    try:
        updated_track = AudioAnalyzerService.run(video_path, material.dialogue)
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        import traceback

        traceback.print_exc()
        return

    end_ts = time.time()
    print(f"✅ 执行完成，耗时: {end_ts - start_ts:.2f}s")  # noqa: E231

    # 3. 结果展示
    print("\n📝 分析结果示例 (Top 5):")
    for i, item in enumerate(updated_track[:5]):
        analysis = item.get("audio_analysis", {})
        print(f"[{i}] {item.get('start_time')}s - {item.get('end_time')}s: {item.get('content')}")
        if analysis:
            print(
                f"   Gender: {analysis.get('gender')} | Pitch: {analysis.get('pitch_level')} ({analysis.get('avg_pitch_hz')}Hz)"  # noqa: E501
            )
            print(
                f"   Speed: {analysis.get('speed_level')} ({analysis.get('chars_per_sec')} char/s) | Vol: {analysis.get('volume_level')}"  # noqa: E501
            )
        else:
            print("   (无分析数据)")
        print("-" * 40)


if __name__ == "__main__":
    run_test()
