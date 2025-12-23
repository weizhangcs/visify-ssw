import json
import os
import sys
import time
from pathlib import Path

import django

from apps.workflow.character_annotation.services.ticket_uploader import VSSCloudService

# ==========================================
# [环境初始化]
# ==========================================
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()
# ==========================================

# ==========================================
# [配置区] 请填入 M2 步骤成功后获得的路径
# ==========================================
# 例如: "tmp/79589aaf-2129-40c7-804c-df6b3ce72a70.json"
SLICES_FILE_PATH = "tmp/79589aaf-2129-40c7-804c-df6b3ce72a70.json"


def main():
    print("🚀 准备发起 Cloud 单点推理测试...")
    print(f"   Target Metadata: {SLICES_FILE_PATH}")

    # 1. 初始化客户端 (自动读取 DB 配置)
    try:
        client = VSSCloudService()
    except Exception as e:
        print(f"❌ 客户端初始化失败: {e}")
        return

    # 2. 组装 Payload
    task_payload = {
        "task_type": "scene_pre_annotator",
        "payload": {
            "video_title": "You Don't See Me",
            "asset_type": "feature_film",  # 根据业务逻辑填充
            "content_genre": "crime_thriller",
            "slices_file_path": SLICES_FILE_PATH,  # [关键] 传递 Metadata 路径
            "visual_model": "gemini-2.5-flash",  # 或从配置读取
            "text_model": "gemini-2.5-flash",
            "lang": "en",
        },
    }

    # 3. 提交任务
    print("\n[1/3] Submitting Task to Cloud...")
    try:
        resp = client.post("/api/v1/tasks/", task_payload)
        task_id = resp.get("id")
        if not task_id:
            raise ValueError("No Task ID returned")
        print(f"✅ Task Submitted! Cloud Task ID: {task_id}")
    except Exception as e:
        print(f"❌ Submission Failed: {e}")
        return

    # 4. 轮询结果 (模拟业务侧的等待)
    print(f"\n[2/3] Polling Status for Task {task_id}...")

    start_time = time.time()
    while True:
        try:
            # VSSCloudService 默认只封装了 post，这里我们复用其 session 和 headers 发起 GET
            url = f"{client.BASE_URL}/api/v1/tasks/{task_id}"
            status_resp = client.session.get(url, headers=client.headers).json()

            status = status_resp.get("status")
            print(f"   ... Status: {status} (Elapsed: {int(time.time() - start_time)}s)")

            if status == "COMPLETED":
                result = status_resp.get("result")
                print("\n[3/3] 🎉 Inference Success!")
                print("=" * 50)
                # 打印前 500 个字符预览，防止刷屏
                print(json.dumps(result, ensure_ascii=False, indent=2)[:2000] + "\n...")
                print("=" * 50)

                # 可选：将结果保存到本地文件以便查看
                save_path = Path("tmp") / f"final_result_{task_id}.json"
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"Full result saved to: {save_path}")
                break

            elif status == "FAILED":
                error = status_resp.get("error", "Unknown Error")
                print(f"\n❌ Task Failed: {error}")
                break

            time.sleep(5)  # 5秒轮询一次

        except KeyboardInterrupt:
            print("\n⚠️ Polling stopped by user.")
            break
        except Exception as e:
            print(f"⚠️ Polling Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
