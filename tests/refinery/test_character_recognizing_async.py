# 文件路径: tests/refinery/test_character_recognizing_async.py
import os
import sys
from pathlib import Path

import django

# 1. 环境初始化
# 根据目录结构 tests/refinery/xxx.py，回溯三层到达根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()

from apps.refinery.models import Material  # noqa: E402
from apps.refinery.tasks import refinery_character_recognition_task  # noqa: E402
from tests.lib.refinery_bootstrap import RefineryAsyncTester  # noqa: E402


def run_character_refine_test(timeout=900):  # 推理任务通常较慢，设置 15 分钟超时
    print("=" * 60)
    print("🎭 Refinery Character Recognition - Async Unit Test")
    print("=" * 60)

    # A. 准入检查：寻找具备结构化对白且角色未识别的物料
    # 逻辑：必须先完成 analyze_text 产出 dialogue_track
    target = Material.objects.filter(dialogue_track__isnull=False).exclude(dialogue_track=[]).first()

    if not target:
        print("❌ Error: No material found with dialogue_track. Please run text analysis test first.")
        return

    print(f"[*] Target ID: {target.id}")
    print(
        f"[*] Initial Dialogue Sample: {target.dialogue_track[0].get('speaker')} - {target.dialogue_track[0].get('text')[:30]}..."  # noqa: E501
    )

    # B. 设置前置状态：触发 FSM 跳转到新定义的状态位
    if target.status != Material.Status.CHARACTER_RECOGNIZING:
        try:
            print(f"[*] Transitioning state: {target.status} -> CHARACTER_RECOGNIZING")
            target.start_character_recognizing()
            target.save()
        except Exception as e:
            print(f"❌ FSM Transition Failed: {e}")
            return

    # C. 异步执行与观测
    try:
        print("[*] Dispatching Task: refinery_character_recognition_task")
        print("[*] Observer active. Waiting for state to return to PENDING via _handle_task_success...")

        # 使用统一的异步测试工具触发 Task 并等待回归 PENDING (决策位)
        RefineryAsyncTester.trigger_and_wait(str(target.id), refinery_character_recognition_task, timeout=timeout)

        # D. 验收：重新获取数据库副本进行语义闭环验证
        final_check = Material.objects.get(id=target.id)
        print("-" * 40)
        print(f"🏁 Final State: {final_check.status}")

        # 验证 1: 检查 dialogue_track 中的角色回填结果
        track = final_check.dialogue_track
        recognized_count = sum(1 for d in track if d.get("speaker") and d.get("speaker") != "Unknown")

        if recognized_count > 0:
            print(f"✅ SEMANTIC SUCCESS: {recognized_count}/{len(track)} lines recognized.")
            # 抽查前 3 条结果
            for i, d in enumerate(track[:3]):
                print(f"   [{i}] Recognized Speaker: {d.get('speaker')} | Text: {d.get('text')[:30]}...")
        else:
            print("❌ FAILED: Speaker fields are still 'Unknown' or empty.")

        # 验证 2: 验证白盒化指标
        if final_check.pipeline_metrics and "character_recognition" in final_check.pipeline_metrics:
            m = final_check.pipeline_metrics["character_recognition"]
            print(f"✅ METRICS CAPTURED: Duration {m.get('duration')}s | Finished at {m.get('finished_at')}")

    except Exception as e:
        print(f"❌ Test Failed: {str(e)}")


if __name__ == "__main__":
    run_character_refine_test()
