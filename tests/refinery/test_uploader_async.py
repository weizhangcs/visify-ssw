# 文件路径: tests/refinery/test_uploader_async.py

from tests.lib.refinery_bootstrap import RefineryAsyncTester, setup_django_env

# 1. 初始化 Django 环境
setup_django_env()

from apps.refinery.models import Material  # noqa: E402
from apps.refinery.tasks import refinery_sync_task  # noqa: E402


def run_frame_sync_test():
    print("=" * 60)
    print("🚀 Refinery Frame Sync - Async Integration Test")
    print("=" * 60)

    # 1. 寻找具备视觉切片数据且待同步的物料
    # 逻辑：必须先完成 Slicing/FrameExtract 才有 frames 供同步
    target = Material.objects.filter(visual_slices__isnull=False).first()
    if not target:
        print("❌ Error: No material with visual_slices found. Please run slicing test first.")
        return

    print(f"[*] Target ID: {target.id}")

    # 2. 检查并设置状态 (使用 FSM transition)
    if target.status != Material.Status.SYNCING:
        try:
            print(f"[*] Transitioning state: {target.status} -> SYNCING")
            target.start_syncing()  # 调用 models.py 中定义的 transition
            target.save()
        except Exception as e:
            print(f"❌ FSM Transition Failed: {e}")
            return

    # 3. 异步执行与观测
    try:
        # 使用统一的异步测试工具触发 Task
        print("[*] Dispatching task. Watch Docker logs for Batch/Progress...")
        RefineryAsyncTester.trigger_and_wait(str(target.id), refinery_sync_task)

        # 4. 验收：重新从数据库获取最新副本
        fresh_material = Material.objects.get(id=target.id)

        print("-" * 40)
        print(f"Final State: {fresh_material.status}")

        # 检查 visual_slices 中的路径回填结果
        slices = fresh_material.visual_slices
        if slices and len(slices) > 0:
            # 抽查第一个切片的第一个 frame 路径
            sample_frame = slices[0].get("frames", [{}])[0]
            cloud_path = sample_frame.get("path", "")

            if cloud_path.startswith("gs://"):
                print("✅ SUCCESS: Frame paths remapped to GCS.")
                print(f"    Sample Cloud Path: {cloud_path}")
            else:
                print(f"❌ FAILED: Path is still local or empty. Value: {cloud_path}")
        else:
            print("❌ FAILED: visual_slices is missing after task.")

    except Exception as e:
        print(f"❌ Test Failed: {str(e)}")


if __name__ == "__main__":
    run_frame_sync_test()
