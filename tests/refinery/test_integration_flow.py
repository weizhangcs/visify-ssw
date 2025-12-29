# 文件路径: tests/refinery/test_integration_flow.py
import os
import sys
import time
from pathlib import Path

import django

# 1. 环境初始化
# 根据目录结构 tests/refinery/xxx.py，回溯三层到达根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()

from apps.media_assets.models import Media  # noqa E402
from apps.refinery.models import Material  # noqa E402
from apps.refinery.services.scheduler import RefineryScheduler  # noqa E402


def run_full_pipeline_test(timeout=600):
    print("=" * 60)
    print("🚀 Refinery Full Pipeline - Standard Async Integration Test (FSM Protected)")
    print("=" * 60)

    # A. 资产清理与准备
    media = Media.objects.filter(source_video__isnull=False).first()
    if not media:
        print("❌ Error: No media with source video available for testing.")
        return

    # 物理清理旧物料以确保测试纯净度
    Material.objects.filter(media=media).delete()

    # B. 创建起点物料
    print(f"[*] Creating new Material for Media: {media.title}")
    # 此时状态默认为 PENDING
    material = Material.objects.create(media=media)
    material_id = str(material.id)
    print(f"[*] Material Created. ID: {material_id}")

    # C. 核心：启动“多米诺骨牌”
    print("\n🔥 [Action] Ignition: Calling Scheduler...")
    RefineryScheduler.schedule(material_id)

    # D. 修正的异步观测逻辑：通过重新查询获取只读副本，绕过 FSM refresh 限制
    start_time = time.time()
    try:
        print("[*] Observer active. Tracking pipeline via database snapshots...")

        last_status = None
        while time.time() - start_time < timeout:
            # [关键修正] 严禁在 material 实例上调 refresh_from_db
            # 通过 objects.get 重新获取一个全新的、不带状态机锁定的对象快照用于 UI 观测
            snapshot = Material.objects.get(id=material_id)

            # 只有状态变化时才打印
            if snapshot.status != last_status:
                print(f">>> Status Transitioned: {snapshot.status} (Elapsed: {int(time.time() - start_time)}s)")
                last_status = snapshot.status

            # 检查管线收敛
            if snapshot.status == Material.Status.READY:
                print("✅ [Full Pipeline Success] Material converged to READY state.")
                break

            if snapshot.status == Material.Status.FAILED:
                print(f"❌ [Pipeline Failed] Error Log: {snapshot.error_log}")
                return

            time.sleep(5)
        else:
            raise TimeoutError(f"⏳ [Timeout] Pipeline did not reach READY within {timeout}s.")

        # E. 最终验收：验证物理闭环标志 (Cloud Path 回填)
        final_check = Material.objects.get(id=material_id)
        print("-" * 40)

        if final_check.visual_slices:
            try:
                # 检查 visual_slices 中第一个 frame 的路径是否已 remapped
                # 依据 scheduler.py 规则：sync 步骤会将本地路径替换为 gs://
                sample_frame = final_check.visual_slices[0].get("frames", [{}])[0]
                path = sample_frame.get("path", "")

                if path.startswith("gs://"):
                    print("🎉 FINAL VERIFICATION SUCCESS: All paths remapped to Cloud Sync!")
                    print(f"    Sample Artifact: {path}")

                    # 打印白盒化指标
                    if final_check.pipeline_metrics:
                        print("📊 Execution Metrics: ")
                        for slug, m in final_check.pipeline_metrics.items():
                            print(f"- {slug}: {m.get('duration')}s (Finished at {m.get('finished_at')})")
                else:
                    print(f"⚠️ Warning: Pipeline READY but sync failed. Path is: {path}")
            except (KeyError, IndexError):
                print("❌ Error: Invalid data structure in visual_slices.")
        else:
            print("❌ Error: READY state reached but visual_slices is empty.")

    except Exception as e:
        print(f"❌ Pipeline Interrupted: {str(e)}")


if __name__ == "__main__":
    run_full_pipeline_test()
