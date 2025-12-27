# 文件路径: tests/refinery/test_slicing_unit_async.py

from tests.lib.refinery_bootstrap import RefineryAsyncTester, setup_django_env

# 初始化
setup_django_env()

from apps.refinery.models import Material  # noqa: E402
from apps.refinery.tasks import refinery_slicing_task  # noqa: E402


def run_slicing_async_test():
    print("=" * 60)
    print("🎬 Refinery Slicing Logic - Async Unit Test")
    print("=" * 60)

    # A. 准入：寻找已具备 Proxy 和 Dialogue 的物料
    target = (
        Material.objects.filter(proxy_video__isnull=False, dialogue_track__isnull=False).exclude(proxy_video="").first()
    )

    if not target:
        print("❌ Error: No material found with both proxy_video and dialogue_track.")
        return

    # B. 设置 FSM 状态
    print(f"[*] Target ID: {target.id}")
    if target.status != Material.Status.SLICING:
        target.start_slicing()
        target.save()
    print(f"[*] Pre-condition: State is {target.status}")

    # C. 异步执行
    try:
        updated_material = RefineryAsyncTester.trigger_and_wait(str(target.id), refinery_slicing_task, timeout=360)

        # D. 验收
        print("-" * 40)
        print(f"Final State: {updated_material.status}")

        slices = updated_material.visual_slices
        if slices and len(slices) > 0:
            print(f"✅ Slicing Successful: Generated {len(slices)} index items.")
            # 抽查第一个切片
            sample = slices[0]
            print(f"   Sample Slice #1: {sample['start_time']}s - {sample['end_time']}s (Type: {sample['type']})")
        else:
            print("❌ Slicing Failed: No index entries generated.")

    except Exception as e:
        print(f"❌ Test Aborted: {str(e)}")


if __name__ == "__main__":
    run_slicing_async_test()
