"""
使用说明 (Usage):
   docker compose -p vss-edge -f docker-compose.base.yml -f docker-compose.dev.yml
   run --rm worker-media python tests/atomflow/dubbing/test_ocr_service.py
   注意: 请确保 input_video_path 文件存在，且代码目录已挂载到容器中。
"""
import os
import sys
import time
from pathlib import Path

# --- 1. 环境引导 (Bootstrap) ---
# 获取当前脚本所在目录，并向上寻找项目根目录，将其加入 sys.path
current_file = Path(__file__).resolve()

# 动态查找项目根目录 (向上寻找直到发现 'apps' 目录，兼容本地和 Docker 路径结构)
project_root = current_file.parent
while not (project_root / "apps").exists() and project_root != project_root.parent:
    project_root = project_root.parent

if str(project_root) not in sys.path:
    print(f"Adding project root to sys.path: {project_root}")
    sys.path.insert(0, str(project_root))

# --- 2. 配置模型路径 (可选) ---
# 如果您的本地开发环境没有 Docker 中的 /app/local_models 路径，
# 请在这里通过环境变量覆盖 constants.py 中的默认值
# os.environ["OCR_MODEL_DIR"] = r"D:\Models\ocr"

# --- 3. 导入服务 ---
try:
    from apps.atomflow.dubbing import constants
    from apps.atomflow.dubbing.services.ocr import OCRService
except ImportError as e:
    print(f"[Error] Import failed: {e}")
    print("请确保项目根目录已正确添加到 PYTHONPATH。")
    sys.exit(1)


def main():
    print("=" * 50)
    print("   OCRService Manual Test")
    print("=" * 50)

    # --- 4. 准备输入输出 ---
    # [配置] 请确保这里指向一个真实存在的视频文件
    input_video_path = project_root / "tests" / "resources" / "test_video.mp4"

    # [智能选择] 如果 gating 测试已经运行过并生成了掩码，优先使用它
    # 这可以模拟 OCR 算子利用语音信息跳过静音帧的优化策略
    gating_mask_path = project_root / "tests" / "testdata" / "output" / "dubbing" / "gating_masks.pt"
    if not gating_mask_path.exists():
        print("[Info] Gating mask not found. OCR will run without audio-based filtering.")
        gating_mask_path = None
    else:
        print(f"[Info] Found gating mask, using it for semantic filtering: {gating_mask_path}")

    # 输出目录
    output_base = project_root / "tests" / "testdata" / "output" / "dubbing" / "ocr_results"
    output_base.mkdir(parents=True, exist_ok=True)

    print(f"\nInput Video: {input_video_path}")
    print(f"Output Dir: {output_base}")
    print(f"Model (OCR): {constants.OCR_DIR}")

    if not input_video_path.exists():
        print(f"\n[Error] 视频文件不存在: {input_video_path}")
        print("请修改脚本中的 input_video_path 变量，或在 tests/resources/ 目录下放置一个 test_video.mp4 文件。")
        input_video_path.parent.mkdir(parents=True, exist_ok=True)
        return

    # --- 5. 执行调用 ---
    try:
        print("\n>>> Starting Service Execution...")
        start_time = time.time()
        print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")

        # 直接调用静态方法 run
        ocr_index_path, llm_csv_path = OCRService.run(
            video_path=input_video_path,
            output_dir=output_base,
            mask_path=str(gating_mask_path) if gating_mask_path else None,
        )

        end_time = time.time()
        duration = end_time - start_time

        print("\n>>> Execution Successful!")
        print(f"End Time:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")  # noqa: E241
        print(f"Duration:   {duration:.2f} seconds")  # noqa: E241, E231

        # --- 6. 验证结果 ---
        print("\n[Verification] Checking output files...")
        if ocr_index_path and os.path.exists(ocr_index_path):
            print(f"  - Inpainting Index CSV created: {ocr_index_path}")  # noqa: E241,E221
        else:
            print("  - Inpainting Index CSV not created (maybe no valid text found).")

        if llm_csv_path and os.path.exists(llm_csv_path):
            print(f"  - LLM Raw Data CSV created:   {llm_csv_path}")  # noqa: E241,E221
        else:
            print("  - LLM Raw Data CSV not created (maybe no text found).")

        # 尝试用 pandas 读取并预览
        try:
            import pandas as pd

            if llm_csv_path and os.path.exists(llm_csv_path):
                print("\n--- LLM Raw Data Preview (Top 5) ---")
                df = pd.read_csv(llm_csv_path)
                print(df.head())
        except ImportError:
            print("\n[Info] pandas is not installed. Skipping CSV preview.")
        except Exception as e:
            print(f"\n[Warning] Could not read or preview CSV file: {e}")

    except Exception as e:
        print(f"\n[Execution Failed] {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
