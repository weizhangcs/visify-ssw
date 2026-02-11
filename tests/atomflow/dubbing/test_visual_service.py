"""
使用说明 (Usage):
   docker compose -p vss-edge -f docker-compose.base.yml -f docker-compose.dev.yml
   run --rm worker-media python tests/atomflow/dubbing/test_visual_service.py
   注意: 请确保 input_video_path 文件存在，且代码目录已挂载到容器中。
"""
import json
import os
import sys
import time
from pathlib import Path

import cv2
import pandas as pd

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
# os.environ["INSIGHTFACE_HOME"] = r"D:\Models\insightface"

# --- 3. 导入服务 ---
try:
    from apps.atomflow.dubbing import constants
    from apps.atomflow.dubbing.services.visual import VisualAnalysisService
except ImportError as e:
    print(f"[Error] Import failed: {e}")
    print("请确保项目根目录已正确添加到 PYTHONPATH。")
    sys.exit(1)


def extract_face_samples(video_path, csv_path, output_dir):
    """
    从视频中提取每个 Person ID 的最高分和最低分的人脸截图
    """
    print("\n[Post-processing] Extracting face samples for verification...")

    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            print("CSV is empty, skipping extraction.")
            return

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"[Error] Could not open video: {video_path}")
            return

        samples_dir = Path(output_dir) / "face_samples"
        samples_dir.mkdir(parents=True, exist_ok=True)

        # 按 person_id 分组
        for pid, group in df.groupby("person_id"):
            # 获取最高分 5 张和最低分 5 张
            top_5 = group.nlargest(5, "score")
            bottom_5 = group.nsmallest(5, "score")

            # 合并并去重 (防止总数少于 10 张时重复)
            samples = pd.concat([top_5, bottom_5]).drop_duplicates()

            for _, row in samples.iterrows():
                frame_idx = int(row["frame_idx"])
                bbox = json.loads(row["bbox"])  # [x1, y1, x2, y2]
                score = row["score"]

                # 读取特定帧
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if ret:
                    x1, y1, x2, y2 = map(int, bbox)
                    # 简单的边界检查
                    h, w = frame.shape[:2]
                    face_img = frame[max(0, y1) : min(h, y2), max(0, x1) : min(w, x2)]

                    filename = f"pid_{pid}_score_{score:.4f}_frame_{frame_idx}.jpg"  # noqa: E231
                    cv2.imwrite(str(samples_dir / filename), face_img)

        cap.release()
        print(f"Face samples saved to: {samples_dir}")

    except Exception as e:
        print(f"[Error] Failed to extract face samples: {e}")
        import traceback

        traceback.print_exc()


def main():
    print("=" * 50)
    print("   VisualAnalysisService Manual Test")
    print("=" * 50)

    # --- 4. 准备输入输出 ---
    # [配置] 请确保这里指向一个真实存在的视频文件
    input_video_path = project_root / "tests/testdata/EP01.mp4"

    # [智能选择] 如果 gating 测试已经运行过并生成了掩码，优先使用它
    # 这可以模拟 Visual 算子利用语音信息跳过静音帧的优化策略
    gating_mask_path = project_root / "tests" / "testdata" / "output" / "dubbing" / "gating_masks.pt"
    if not gating_mask_path.exists():
        print("[Info] Gating mask not found. Visual Analysis will run without audio-based filtering.")
        gating_mask_path = None
    else:
        print(f"[Info] Found gating mask, using it for semantic filtering: {gating_mask_path}")

    # 输出目录
    output_base = project_root / "tests" / "testdata" / "output" / "dubbing" / "visual_results"
    temp_dir = output_base / "temp"
    output_base.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    print(f"Input Video: {input_video_path}")
    print(f"Output Dir:  {output_base}")  # noqa: E241
    print(f"Temp Dir:    {temp_dir}")  # noqa: E241
    print(f"Model (InsightFace): {constants.INSIGHTFACE_MODEL_DIR}")

    if not input_video_path.exists():
        print(f"\n[Error] 视频文件不存在: {input_video_path}")
        print("请修改脚本中的 input_video_path 变量，或在 tests/resources/ 目录下放置一个 test_video.mp4 文件。")
        # 尝试创建目录方便用户放置文件
        input_video_path.parent.mkdir(parents=True, exist_ok=True)
        return

    # --- 5. 执行调用 ---
    try:
        print("\n>>> Starting Service Execution...")
        start_time = time.time()
        print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")

        # 直接调用静态方法 run
        csv_path = VisualAnalysisService.run(
            video_path=input_video_path,
            output_dir=output_base,
            temp_dir=temp_dir,
            mask_path=str(gating_mask_path) if gating_mask_path else None,
        )

        end_time = time.time()
        duration = end_time - start_time

        print("\n>>> Execution Successful!")
        print(f"End Time:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")  # noqa: E241
        print(f"Duration:   {duration:.2f} seconds")  # noqa: E241, E231
        print(f"Result CSV: {csv_path}")

        # --- 6. 验证结果 ---
        if csv_path and os.path.exists(csv_path):
            print("\n[Verification] Loading result CSV...")
            try:
                df = pd.read_csv(csv_path)
                print(f"Total Faces Detected: {len(df)}")
                if not df.empty:
                    print("\n--- First 5 Rows Preview ---")
                    print(df.head())
                    print("\n--- Unique Person IDs ---")
                    print(df["person_id"].unique())
            except Exception as e:
                print(f"[Warning] Failed to read CSV: {e}")

            # --- 7. 后处理：提取截图 ---
            extract_face_samples(input_video_path, csv_path, output_base)

    except Exception as e:
        print(f"\n[Execution Failed] {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
