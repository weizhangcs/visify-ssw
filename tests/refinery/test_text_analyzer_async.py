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
        # 1. 触发并等待（Tester 内部会轮询数据库）
        RefineryAsyncTester.trigger_and_wait(str(target.id), refinery_analyze_text_task)

        # 2. 【核心修正】彻底抛弃旧的 target 实例，从数据库重新捞取最新的副本
        # 这样既保证了数据的绝对新鲜，又不会破坏 FSM 的实例状态
        fresh_material = Material.objects.get(id=target.id)

        # 3. 验收
        print("-" * 40)
        print(f"Final State: {fresh_material.status}")

        track = fresh_material.dialogue_track
        if isinstance(track, list):
            print(f"✅ SUCCESS: {len(track)} dialogue entries refined into JSONB.")
        else:
            print(f"❌ FAILED: Still empty. Value: {track}")

    except Exception as e:
        print(f"❌ Test Failed: {str(e)}")


if __name__ == "__main__":
    run_text_analysis_test()
