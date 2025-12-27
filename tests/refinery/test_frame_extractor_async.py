# 文件路径: tests/refinery/test_frame_extractor_async.py

from pathlib import Path

from django.conf import settings

from tests.lib.refinery_bootstrap import RefineryAsyncTester, setup_django_env

setup_django_env()

from apps.refinery.models import Material  # noqa E402
from apps.refinery.tasks import refinery_frame_extracting_task  # noqa E402


def run_frame_test():
    print("=" * 60)
    print("📸 Refinery Frame Extractor - Async Unit Test")
    print("=" * 60)

    # 1. 寻找已具备逻辑切片的物料
    target = Material.objects.filter(visual_slices__isnull=False).exclude(visual_slices=[]).first()

    if not target:
        print("❌ Error: No material found with logical slices. Run Slicing test first.")
        return

    # 2. 设置状态
    if target.status != Material.Status.FRAME_EXTRACTING:
        target.start_frame_extracting()
        target.save()

    try:
        updated = RefineryAsyncTester.trigger_and_wait(
            str(target.id), refinery_frame_extracting_task, timeout=600  # 2933 个切片抽帧会很久，请耐心等待
        )

        # 3. 物理验收
        print("-" * 40)
        slices = updated.visual_slices
        if slices and "frames" in slices[0] and len(slices[0]["frames"]) > 0:
            rel_path = slices[0]["frames"][0]["path"]
            abs_path = Path(settings.MEDIA_ROOT) / rel_path
            print(f"✅ Success: Path recorded -> {rel_path}")
            if abs_path.exists():
                print("✅ Success: Physical file verified on disk.")
            else:
                print(f"❌ Error: Path recorded but file MISSING at {abs_path}")
        else:
            print("❌ Error: No frame data backfilled in visual_slices.")

    except Exception as e:
        print(f"❌ Test Failed: {str(e)}")


if __name__ == "__main__":
    run_frame_test()
