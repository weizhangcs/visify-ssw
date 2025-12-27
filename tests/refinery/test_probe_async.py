# 文件路径: tests/refinery/test_probe_async.py

from tests.lib.refinery_bootstrap import RefineryAsyncTester, setup_django_env

# 1. 环境初始化
setup_django_env()

# 2. 延迟导入业务模块
from apps.media_assets.models import Media  # noqa: E402
from apps.refinery.models import Material  # noqa: E402
from apps.refinery.tasks import refinery_probe_task  # noqa: E402


def run_async_probe_test():
    print("=" * 60)
    print("🔭 Refinery Probe & Waveform - Async Starting Point Test")
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

    # B. 设置前置状态
    print(f"[*] Target ID: {material.id}")
    if material.status != Material.Status.PROBING:
        material.start_probing()
        material.save()
    print(f"[*] Pre-condition: State is {material.status}")

    # C. 异步执行并轮询结果
    try:
        # 使用你之前的 observer 范式
        updated_material = RefineryAsyncTester.trigger_and_wait(
            str(material.id), refinery_probe_task, timeout=180  # 声纹计算可能较慢，给予充足时间
        )

        # D. 数据正确性验收 (最高验收人标准)
        print("-" * 40)
        print(f"Final State: {updated_material.status}")

        # 1. 验证元数据
        if updated_material.tech_meta:
            print(f"✅ Tech Meta Captured: {updated_material.tech_meta.get('container')}")
        else:
            print("❌ Tech Meta Missing!")

        # 2. 验证声纹数据 (JSONB 字段验收)
        wf_data = updated_material.waveform_data
        if wf_data and isinstance(wf_data, dict) and "data" in wf_data:
            peaks_count = len(wf_data["data"])
            print(f"✅ Waveform Data Refined: {peaks_count} peaks captured into JSONB.")
        else:
            print("❌ Waveform Data missing or invalid format in JSONB!")

    except Exception as e:
        print(f"❌ Test Failed: {str(e)}")


if __name__ == "__main__":
    run_async_probe_test()
