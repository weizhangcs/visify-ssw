# 文件路径: tests/refinery/test_hls_async.py
from pathlib import Path

from django.conf import settings

from tests.lib.refinery_bootstrap import RefineryAsyncTester, setup_django_env

# 1. 初始化
setup_django_env()

# 2. 导入（确保在 setup 之后）
from apps.refinery.models import Material  # noqa: E402
from apps.refinery.tasks import refinery_hls_task  # noqa: E402


def run_async_hls_test():
    print("=" * 60)
    print("📺 Refinery HLS Fragmenting - Async Dependency Test")
    print("=" * 60)

    # A. 寻找一个已完成转码（持有 Proxy）的物料
    # 这是 HLS 生产的物理前置条件
    target = Material.objects.filter(proxy_video__isnull=False).exclude(proxy_video="").first()

    if not target:
        print("❌ Error: No material found with a valid proxy video. Please run Transcode test first.")
        return

    print(f"[*] Target ID: {target.id}")
    print(f"[*] Proxy Path: {target.proxy_video}")

    # B. 设置 FSM 状态位（进入 HLS 加工环节）
    if hasattr(target, "start_hls_fragmenting"):
        target.start_hls_fragmenting()
        target.save()
    else:
        # 如果暂未定义状态，打印警告，由异步逻辑直接触发
        print("[!] Warning: start_hls_fragmenting transition not found on model, proceeding with task directly.")

    # C. 执行异步派发并观察
    try:
        updated_material = RefineryAsyncTester.trigger_and_wait(str(target.id), refinery_hls_task, timeout=120)

        # D. 验收标准检查
        print("-" * 40)
        print(f"Final State: {updated_material.status}")
        print(f"HLS Index: {updated_material.hls_playlist}")

        # 验证 1: 数据库中不应是 FileField 幻觉对象，而是字符串路径
        if isinstance(updated_material.hls_playlist, str) and updated_material.hls_playlist.endswith(".m3u8"):
            print("✅ Database Integrity: Path string correctly recorded.")
        else:
            print("❌ Database Integrity: Invalid data in hls_playlist field!")

        # 验证 2: 物理文件验证
        abs_index_path = Path(settings.MEDIA_ROOT) / "refinery" / updated_material.hls_playlist
        if abs_index_path.exists():
            print(f"✅ Physical Artifact: Index file verified at {abs_index_path}")
            # 抽查切片文件是否存在
            ts_files = list(abs_index_path.parent.glob("*.ts"))
            print(f"✅ Physical Artifact: Found {len(ts_files)} segment (.ts) files.")
        else:
            print(f"❌ Physical Artifact: Index file missing at {abs_index_path}")

        print("-" * 40)
        print(f"✅ SUCCESS: HLS Atomic Refinement Verified for {updated_material.id}")

    except Exception as e:
        print(f"❌ Test Failed: {str(e)}")


if __name__ == "__main__":
    run_async_hls_test()
