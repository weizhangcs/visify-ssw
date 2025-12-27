# tests/refinery/test_transcode_async.py
from tests.lib.refinery_bootstrap import RefineryAsyncTester, setup_django_env

# 初始化 Django 环境
setup_django_env()

from apps.media_assets.models import Media  # noqa: E402
from apps.refinery.models import Material  # noqa: E402
from apps.refinery.tasks import refinery_transcode_task  # noqa: E402


def run_async_transcode_test():
    print("=" * 60)
    print("🎬 Refinery Transcode - Real Async Verification")
    print("=" * 60)

    # A. 寻找一个有源视频但还没有对应 Material 的 Media
    # 这模拟了媒资新入库后，Refinery 首次介入的场景
    media = Media.objects.filter(source_video__isnull=False, material__isnull=True).first()

    if not media:
        # 兜底：如果所有 Media 都有了 Material，则找一个现成的并物理清理掉，以模拟“新物料”
        media = Media.objects.filter(source_video__isnull=False).first()
        if media and hasattr(media, "material"):
            print(f"[*] Cleaning existing material for Media: {media.title}")
            media.material.delete()

    if not media:
        print("❌ Error: No media with source video available for testing.")
        return

    # B. 物理创建物料 (Refinery 的起点)
    print(f"[*] Creating new Material for Media: {media.title} (ID: {media.id})")
    material = Material.objects.create(media=media)

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
        print(f"Proxy File: {updated_material.proxy_video}")

    except Exception as e:
        print(f"❌ Test Aborted: {str(e)}")


if __name__ == "__main__":
    run_async_transcode_test()
