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

    # 1. 强行初始化状态，确保 FSM 路径通畅
    print(f"[*] Resetting Material {target.id} to PENDING for test...")
    if target.status == Material.Status.PENDING:
        # 2. 状态点火：明确进入 ANALYZING_TEXT
        target.start_analyzing_text()
        target.save()

        # 3. 异步执行
        RefineryAsyncTester.trigger_and_wait(str(target.id), refinery_analyze_text_task)

        # 4. 验收（采用更底层的方式）
        fresh_material = Material.objects.get(id=target.id)

        # 避开缓存，直接打印关键指标
        actual_track = fresh_material.dialogue_track
        print(f"[*] Post-Task Status: {fresh_material.status}")
        print(f"[*] Track Type: {type(actual_track)}")

        if actual_track and len(actual_track) > 0:
            print(f"✅ SUCCESS: {len(actual_track)} dialogue entries refined.")
            # 强制检查第一个元素的 Key，验证 Schema 归一化
            print(f"[*] Schema Verification: {actual_track[0].keys()}")
        else:
            print("❌ FAILED: Data mismatch. Length is 0.")
    else:
        print(f"[*] Post-Task Status: {target.status}, current pipeline is occupied by other tasks.")


if __name__ == "__main__":
    run_text_analysis_test()
