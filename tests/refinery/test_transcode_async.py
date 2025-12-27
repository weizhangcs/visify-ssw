# tests/refinery/test_transcode_async.py
from tests.lib.refinery_bootstrap import RefineryAsyncTester, setup_django_env

# 初始化 Django 环境
setup_django_env()

from apps.refinery.models import Material  # noqa: E402
from apps.refinery.tasks import refinery_transcode_task  # noqa: E402


def run_async_transcode_test():
    print("=" * 60)
    print("🎬 Refinery Transcode - Real Async Verification")
    print("=" * 60)

    # 1. 寻找测试素材
    material = Material.objects.filter(media__source_video__isnull=False).first()
    if not material:
        print("Error: No test media found.")
        return

    # 2. 初始化 FSM 状态
    print(f"[*] Target Material: {material.id}")
    if material.status != Material.Status.TRANSCODING:
        material.start_transcoding()
        material.save()
    print(f"[*] Pre-condition: State is {material.status}")

    # 3. 执行异步验证
    try:
        updated_material = RefineryAsyncTester.trigger_and_wait(str(material.id), refinery_transcode_task)

        # 4. 最终物理检查
        print("-" * 40)
        print(f"Final State: {updated_material.status}")
        print(f"Proxy File: {updated_material.proxy_video.name}")
        print(f"Duration: {updated_material.duration}s")

        # 验证物理文件是否存在
        if updated_material.proxy_video.storage.exists(updated_material.proxy_video.name):
            print("✅ Artifact Existence: Verified in Storage.")
        else:
            print("❌ Artifact Existence: File missing in storage!")

    except Exception as e:
        print(f"❌ Test Aborted: {str(e)}")


if __name__ == "__main__":
    run_async_transcode_test()
