# tests/manual_test_uploader.py
import logging
import os
import shutil
import sys
from pathlib import Path

import django

# 如果需要手动修改配置用于测试，可以导入模型
from apps.configuration.models import IntegrationSettings

# [注意] 只有在 django.setup() 之后才能导入业务模块
from apps.workflow.character_annotation.services.edge_scene_processor import EdgeScenePreprocessor

# ==========================================
# [关键修复] 初始化 Django 环境
# ==========================================
# 1. 将项目根目录加入 Python 路径，确保能找到 visify_ssw 模块
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))

# 2. 设置 Django settings 环境变量
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")

# 3. 启动 Django (加载 App Registry)
django.setup()
# ==========================================


logging.basicConfig(level=logging.INFO)

VIDEO_PATH = "/app/media_root/transcoding_outputs/c2c81885-7eb4-46f2-9c92-d2018be28b74/265/proxy.mp4"
ASS_PATH = "/app/media_root/character_annotation/outputs/2025/12/23/EP02_ai.ass"
WORK_DIR = Path("/app/tests/testdata/m2_test/NowYouSeeMe")


def main():
    # 0. 检查数据库配置是否就绪
    try:
        settings = IntegrationSettings.get_solo()
        if not settings.cloud_api_key or not settings.cloud_instance_id:
            print("❌ 错误: 数据库 IntegrationSettings 表中缺少 cloud_api_key 或 cloud_instance_id")
            print("   请先在 Admin 后台或数据库中配置这些值。")
            return
        print(f"✅ 加载配置成功: Instance ID = {settings.cloud_instance_id}")
    except Exception as e:
        print(f"❌ 无法读取数据库配置: {e}")
        return

    # 1. 准备目录
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    print("🚀 开始 M2 传输层测试...")
    print(f"   视频源: {VIDEO_PATH}")
    print(f"   字幕源: {ASS_PATH}")

    # 2. 实例化处理器 (自动从 DB 读取配置)
    processor = EdgeScenePreprocessor(work_dir=WORK_DIR, asset_id="test-asset-uuid-002", media_id="test-media-uuid-002")

    # 3. 执行全流程
    try:
        # 注意：确保传入的是字符串路径
        result = processor.process(str(VIDEO_PATH), str(ASS_PATH))

        print("\n🎉 M2 验证成功!")
        print("------------------------------------------------")
        print(f"Cloud Metadata Path : {result['slices_file_path']}")
        print(f"Total Slices        : {result['total_slices']}")
        print("------------------------------------------------")
        print("请检查:")
        print("1. Cloud GCS Bucket 是否有对应图片")
        print("2. Cloud 本地存储 (tmp/) 是否有 json 文件")

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
