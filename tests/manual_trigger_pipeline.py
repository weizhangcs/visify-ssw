import os
import sys
from pathlib import Path

import django

# 业务导入必须在 setup() 之后
from apps.workflow.scene_annotation.models import SceneAnnotationProject
from apps.workflow.scene_annotation.tasks import run_scene_annotation_pipeline

# ==========================================
# [环境初始化] 让脚本能加载 Django 环境
# ==========================================
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()
# ==========================================


# --- 配置参数 (根据您的实际环境修改) ---
ASSET_ID = "test-asset-uuid-003"
MEDIA_ID = "test-media-uuid-003"
# 确保这些路径在 worker-media 容器内存在
VIDEO_PATH = "/app/media_root/transcoding_outputs/c2c81885-7eb4-46f2-9c92-d2018be28b74/265/proxy.mp4"
ASS_PATH = "/app/media_root/character_annotation/outputs/2025/12/23/EP02_ai.ass"


def main():
    print("🚀 准备触发 M3 全流程测试...")
    print(f"   Asset ID: {ASSET_ID}")
    print(f"   Video: {VIDEO_PATH}")

    # 1. 准备数据: 确保 Project 存在
    project, created = SceneAnnotationProject.objects.get_or_create(
        asset_id=ASSET_ID, defaults={"title": "M3 Script Trigger Test"}
    )
    if created:
        print(f"   [System] Created new Project: {project}")
    else:
        print(f"   [System] Using existing Project: {project}")

    # 2. 异步触发 Celery 任务
    print("   [Action] Dispatching task to Celery (queue: worker-media)...")

    try:
        # 使用 delay() 异步调用
        async_result = run_scene_annotation_pipeline.delay(
            project_id=project.id, media_id=MEDIA_ID, video_path=VIDEO_PATH, ass_path=ASS_PATH
        )

        print("-" * 50)
        print("✅ 任务发送成功！")
        print(f"   Celery Task ID: {async_result.id}")
        print("-" * 50)
        print("下一步：请立即检查 worker-media 的日志以确认执行情况：")
        print("命令: docker compose -p vss-edge logs -f --tail=100 worker-media")

    except Exception as e:
        print(f"❌ 任务发送失败: {e}")


if __name__ == "__main__":
    main()
