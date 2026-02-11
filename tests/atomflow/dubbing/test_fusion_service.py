"""
使用说明 (Usage):
   docker compose -p vss-edge -f docker-compose.base.yml -f docker-compose.dev.yml
   run --rm worker-media python tests/atomflow/dubbing/test_fusion_service.py
   注意: 请确保前序步骤 (Gating, Visual, Script Refinement) 的测试产物存在。
"""
import json
import sys
import time
from pathlib import Path

# --- 1. 环境引导 (Bootstrap) ---
# 获取当前脚本所在目录，并向上寻找项目根目录，将其加入 sys.path
current_file = Path(__file__).resolve()
project_root = current_file.parent
while not (project_root / "apps").exists() and project_root != project_root.parent:
    project_root = project_root.parent

if str(project_root) not in sys.path:
    print(f"Adding project root to sys.path: {project_root}")
    sys.path.insert(0, str(project_root))

# --- 2. 导入服务 ---
try:
    from apps.atomflow.dubbing.services.fusion import AudioVisualFusionService
except ImportError as e:
    print(f"[Error] Import failed: {e}")
    print("请确保项目根目录已正确添加到 PYTHONPATH。")
    sys.exit(1)


def main():
    print("=" * 50)
    print("   AudioVisualFusionService Manual Test")
    print("=" * 50)

    # --- 3. 准备输入 ---
    test_data_dir = project_root / "tests" / "testdata" / "output" / "dubbing"

    # 3.1 Script Refinement Result (Metadata)
    # [Optimization] 使用精修后的脚本作为 Fusion 的输入，以获得更准确的时间轴和召回内容
    script_json_path = test_data_dir / "script_refinement_result.json"
    if not script_json_path.exists():
        print(f"[Error] Script Refinement result not found: {script_json_path}")
        print("请先运行 test_script_refinement_service.py 生成精修脚本。")
        return

    with open(script_json_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)
        raw_segments = script_data.get("refined_script", [])

        # 过滤掉噪音片段 (DISCARD_NOISE)
        metadata = [seg for seg in raw_segments if seg.get("source_of_truth") != "DISCARD_NOISE"]
        print(
            f"[Input] Loaded {len(metadata)} segments from script refinement result (filtered {len(raw_segments) - len(metadata)} noise segments)."  # noqa: E501
        )

    # 3.2 Visual Result (Face CSV)
    face_csv_path = test_data_dir / "visual_results" / "face_index_with_clusters.csv"
    if not face_csv_path.exists():
        print(f"[Error] Visual result not found: {face_csv_path}")
        print("请先运行 test_visual_service.py 生成人脸分析结果。")
        return
    print(f"[Input] Face CSV: {face_csv_path}")

    # 3.3 Audio Path (Perception Track)
    # 优先使用 gating 产出的纯净语音，因为它与 perception 结果对齐
    audio_path = test_data_dir / "gating_speech_only.wav"
    if not audio_path.exists():
        # 如果没有 gating 产物，尝试寻找原始测试文件 (根据之前的测试脚本推断路径)
        print("[Warning] Gating output not found, trying original source...")
        audio_path = (
            project_root
            / "media_root/dubbing/3d30b544-fd12-4f65-9000-3216b9984ad6/EP01_(Vocals)_model_bs_roformer_ep_317_sdr_12.wav"  # noqa: E501
        )

    if not audio_path.exists():
        print(f"[Error] Audio file not found: {audio_path}")
        print("请确保 test_gating_service.py 已运行，或手动指定一个有效的音频路径。")
        return
    print(f"[Input] Audio Path: {audio_path}")

    # 输出路径
    output_json_path = test_data_dir / "fusion_result.json"

    # --- 4. 执行调用 ---
    try:
        print("\n>>> Starting Service Execution...")
        start_time = time.time()
        print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")

        # 直接调用静态方法 run
        fused_metadata = AudioVisualFusionService.run(
            metadata=metadata, face_csv_path=face_csv_path, audio_path=audio_path
        )

        end_time = time.time()
        duration = end_time - start_time

        print("\n>>> Execution Successful!")
        print(f"End Time:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")  # noqa: E241
        print(f"Duration:   {duration:.2f} seconds")  # noqa: E241, E231

        # --- 5. 验证与保存 ---
        # 统计说话人分布
        speaker_counts = {}
        for seg in fused_metadata:
            spk = seg.get("speaker", "UNKNOWN")
            speaker_counts[spk] = speaker_counts.get(spk, 0) + 1

        print("\n[Verification] Speaker Distribution:")
        for spk, count in speaker_counts.items():
            print(f"  - {spk}: {count} segments")  # noqa: E221

        # 保存结果
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(fused_metadata, f, ensure_ascii=False, indent=2)
        print(f"\nResult saved to: {output_json_path}")

    except Exception as e:
        print(f"\n[Execution Failed] {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
