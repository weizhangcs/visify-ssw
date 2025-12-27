# tests/lib/refinery_bootstrap.py
import os
import sys
import time
from pathlib import Path

import django


def setup_django_env():
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.append(str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
    django.setup()


class RefineryAsyncTester:
    """
    异步任务验证器：强制通过 Celery 派发并观察数据库状态变更
    """

    @staticmethod
    def trigger_and_wait(material_id, task_obj, timeout=300):
        """
        :param material_id: 物料 UUID
        :param task_obj: Celery Task 对象 (例如 refinery_transcode_task)
        :param timeout: 最大等待时间（秒）
        """
        from apps.refinery.models import Material

        print(f"\n🚀 [Async Test] Dispatching {task_obj.name} for ID: {material_id}")

        # 1. 真实异步派发
        # 此时任务会进入 Redis，由独立进程 worker-media 消费
        task_obj.delay(material_id)

        # 2. 观察者模式：轮询数据库快照
        start_time = time.time()
        print("[*] Observer started. Waiting for state to return to PENDING...")

        while time.time() - start_time < timeout:
            # 必须重新从 DB 获取实例以查看物理状态机变更
            material = Material.objects.get(id=material_id)

            # 关键判定：当观察到状态回归 PENDING 时，说明异步任务已执行完毕并成功触发了 finish_current_task()
            if material.status == Material.Status.PENDING:
                elapsed = int(time.time() - start_time)
                print(f"✅ [Async Success] Callback captured! Task finished in {elapsed}s.")
                return material

            if material.status == Material.Status.FAILED:
                print(f"❌ [Async Failed] Material entered FAILED state. Log: {material.error_log}")
                return material

            # 每隔 10 秒采样一次
            time.sleep(10)
            elapsed = int(time.time() - start_time)
            print(
                f"✅ [Async Processing] Material entered PROCESSING(TRANSCODE/PROBING...etc) state. spent: {elapsed}s."
            )

        raise TimeoutError(f"⏳ [Async Timeout] Task {task_obj.name} did not complete within {timeout}s.")
