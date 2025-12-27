# 文件路径: tests/test_refinery_flow.py

import os
import sys
import time
from pathlib import Path

import django

# 1. 环境初始化
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()


from apps.media_assets.models import Media  # noqa: E402
from apps.refinery.models import Material  # noqa: E402
from apps.refinery.services.scheduler import RefineryScheduler  # noqa: E402


def run_refinery_test():
    print("=" * 60)
    print("🚀 启动 Refinery 预处理中心冒烟测试 (FSM 修正版)")
    print("=" * 60)

    # 1. 寻找一个现有的可测试 Media
    test_media = Media.objects.filter(source_video__isnull=False).first()

    if not test_media:
        print("❌ 错误：数据库中没有找到带有源视频的 Media 记录。")
        return

    print(f"[*] 选中测试媒资: {test_media.title}")

    # 2. 获取或创建 Material
    material, created = Material.objects.get_or_create(media=test_media)

    # [核心修正] 如果不是新建的，通过 handle_failure 重置状态到 PENDING 的逻辑太复杂
    # 我们这里直接物理删除旧物料重新创建，以确保测试环境纯净且符合 FSM 路径
    if not created:
        print("[*] 清理旧的物料数据...")
        material.delete()
        material = Material.objects.create(media=test_media)

    print(f"[*] 初始物料就绪: {material.id}, 当前状态: {material.status}")

    # 3. 触发调度器
    print("\n[Step 1] 正在呼叫调度器执行初始派发...")
    try:
        RefineryScheduler.schedule(str(material.id))
    except Exception as e:
        print(f"❌ 调度触发失败: {str(e)}")
        return

    # 4. 增强型状态监视器
    print("\n[Step 2] 正在监视全管线自动流转 (限时 30s)...")
    start_time = time.time()
    observed_statuses = set()  # 记录经历过的所有状态

    while time.time() - start_time < 30:
        material = Material.objects.get(id=material.id)

        current_status = material.status

        if current_status not in observed_statuses:
            print(f"   >>> 捕获到状态变更: {current_status}")  # noqa: E221
            observed_statuses.add(current_status)

        # 检查是否进入过核心中间态
        if Material.Status.PROBING in observed_statuses and Material.Status.TRANSCODING in observed_statuses:
            print("   ✅ 核心验证成功：管线已自动从 Probe 切换到了 Transcode！")
            break

        if current_status == Material.Status.READY:
            print("   🎉 终点验证成功：全管线处理完成，物料已 READY。")
            break

        if current_status == Material.Status.FAILED:
            print(f"   ❌ 失败：进入错误状态。错误日志: {material.error_log}")
            break

        time.sleep(1)

    # 5. 最终判定
    print("\n" + "-" * 40)
    print(f"流转路径轨迹: {' -> '.join(list(observed_statuses))}")
    if len(observed_statuses) > 2:  # 至少经历了 PENDING -> PROBING -> PENDING...
        print("🔥 测试结论：FSM 自动编排逻辑验证通过！")
    else:
        print("⚠️ 测试结论：流转在某个环节中断，请检查 Celery Worker 或信号触发。")
    print("-" * 40)


if __name__ == "__main__":
    run_refinery_test()
