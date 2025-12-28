import sys
from pathlib import Path

from apps.refinery.services.uploader import TicketUploader, VSSCloudService

# 模拟环境
sys.path.append(str(Path(__file__).resolve().parents[2]))


def run_standalone_test(total_count=1200):
    # 1. 配置测试数据（请根据实际云端环境修改）
    TEST_CONFIG = {
        "base_url": "http://10.168.1.90:8001",
        "api_key": "394fcded-4cdc-44e9-a3e9-a3b437795035",
        "instance_id": "c5e2d07f-0003-46c2-8af2-1e91c68f637f",
        "material_id": "a230d904-fc2f-4262-a2c9-1b48e587e6dc",
        "asset_id": "c2c81885-7eb4-46f2-9c92-d2018be28b74",
    }

    # 2. 准备本地测试文件 (模拟 5 个小图片)
    test_dir = Path("media_root/refinery/frames/a230d904-fc2f-4262-a2c9-1b48e587e6dc")
    test_dir.mkdir(exist_ok=True)
    test_files = []
    for i in range(total_count):
        f = test_dir / f"frame_{i:04d}.jpg"  # noqa : E231
        f.write_text(f"dummy data for frame {i}")
        test_files.append(f)

    print(f"[*] Prepared {len(test_files)} files for testing.")

    # 3. 初始化服务
    service = VSSCloudService(
        base_url=TEST_CONFIG["base_url"], api_key=TEST_CONFIG["api_key"], instance_id=TEST_CONFIG["instance_id"]
    )

    uploader = TicketUploader(
        material_id=TEST_CONFIG["material_id"], asset_id=TEST_CONFIG["asset_id"], cloud_client=service
    )

    # 4. 执行上传测试
    print("🚀 Starting Standalone Upload Test...")
    try:
        mapping = uploader.upload_files(test_files)
        print("\n✅ Upload Success!")
        for local, remote in mapping.items():
            print(f"- {Path(local).name} -> {remote}")
    except Exception as e:
        print(f"\n❌ Upload Failed: {str(e)}")


if __name__ == "__main__":
    run_standalone_test()
