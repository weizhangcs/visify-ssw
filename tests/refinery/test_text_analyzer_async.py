# 文件路径: tests/refinery/test_text_analyzer_async.py

from tests.lib.refinery_bootstrap import RefineryAsyncTester, setup_django_env

# 初始化
setup_django_env()

from apps.refinery.models import Material  # noqa: E402
from apps.refinery.tasks import refinery_analyze_text_task  # noqa: E402


def run_text_analysis_test():
    print("=" * 60)
    print("📝 Refinery Text Analysis - Async Unit Test")
    print("=" * 60)

    # 1. 寻找有字幕路径的物料
    target = Material.objects.filter(media__source_subtitle__isnull=False).first()
    if not target:
        print("❌ Error: No material with media.source_subtitle found.")
        return

    # 2. 设置状态
    print(f"[*] Target ID: {target.id}")
    if target.status != Material.Status.PENDING:
        target.start_analyzing_text()  # 假设模型有此方法
        target.save()

    # 3. 异步执行
    try:
        updated = RefineryAsyncTester.trigger_and_wait(str(target.id), refinery_analyze_text_task)

        # 4. 验收
        print("-" * 40)
        print(f"Final State: {updated.status}")
        track = updated.dialogue_track
        if track and len(track) > 0:
            print(f"✅ SUCCESS: {len(track)} dialogue entries refined into JSONB.")
            print(f"   First Line: [{track[0]['speaker']}] {track[0]['text']}")
        else:
            print("❌ FAILED: dialogue_track is empty.")

    except Exception as e:
        print(f"❌ Test Failed: {str(e)}")


if __name__ == "__main__":
    run_text_analysis_test()
