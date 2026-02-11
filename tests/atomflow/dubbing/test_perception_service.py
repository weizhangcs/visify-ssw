"""
使用说明 (Usage):
   docker compose -p vss-edge -f docker-compose.base.yml -f docker-compose.dev.yml
   run --rm worker-media python tests/atomflow/dubbing/test_perception_service.py
   注意: 请确保 input_audio_path 文件存在，且代码目录已挂载到容器中。
"""
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
# os.environ["WHISPER_MODEL_PATH"] = r"D:\Models\whisper"

# --- 3. 导入服务 ---
try:
    from apps.atomflow.dubbing import constants
    from apps.atomflow.dubbing.services.perception import PerceptionAnalyzerService
except ImportError as e:
    print(f"[Error] Import failed: {e}")
    print("请确保项目根目录已正确添加到 PYTHONPATH。")
    sys.exit(1)


def main():
    print("=" * 50)
    print("   PerceptionAnalyzerService Manual Test")
    print("=" * 50)

    # --- 4. 准备输入输出 ---
    # 默认输入路径 (与 gating 测试保持一致)
    default_input = project_root / "tests/testdata/output/dubbing/gating_speech_only.wav"

    # [智能选择] 如果 gating 测试已经运行过并生成了纯净语音，优先使用它
    # 因为 Perception 服务通常是在 Gating 和 Denoise 之后运行的
    # gating_output = project_root / "tests/testdata/output/dubbing/gating_speech_only.wav"
    gating_output = (
        project_root
        / "media_root/dubbing/3d30b544-fd12-4f65-9000-3216b9984ad6/EP01_(Vocals)_model_bs_roformer_ep_317_sdr_12.wav"
    )

    if gating_output.exists():
        print(f"[Info] Found gating output, using it as input for better accuracy: {gating_output}")
        input_audio_path = gating_output
    else:
        input_audio_path = default_input

    # 输出目录
    output_base = project_root / "tests/testdata/output/dubbing"
    output_base.mkdir(parents=True, exist_ok=True)
    output_json_path = output_base / "perception_result.json"

    print(f"Input Audio: {input_audio_path}")
    print(f"Output JSON: {output_json_path}")
    print(f"Model (Whisper): {constants.WHISPER_PATH}")

    if not input_audio_path.exists():
        print(f"\n[Error] 文件不存在: {input_audio_path}")
        print("请修改脚本中的 input_audio_path 变量，指向一个有效的音频文件。")
        return

    # --- 5. 执行调用 ---
    try:
        print("\n>>> Starting Service Execution...")
        start_time = time.time()
        print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")

        # 直接调用静态方法 run
        result = PerceptionAnalyzerService.run(audio_path=str(input_audio_path), output_path=str(output_json_path))

        end_time = time.time()
        duration = end_time - start_time

        print("\n>>> Execution Successful!")
        print(f"End Time:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")  # noqa: E241
        print(f"Duration:   {duration:.2f} seconds")  # noqa: E231,E241

        # --- 6. 验证结果 ---
        segments = result.get("segments", [])
        print(f"\n[Verification] Transcribed {len(segments)} segments.")

        if segments:
            print("\n--- First 3 Segments Preview ---")
            for i, seg in enumerate(segments[:3]):
                print(
                    f"[{i+1}] {seg['start']:.2f}s -> {seg['end']:.2f}s | Conf: {seg.get('confidence', 0):.2f} | Text: {seg['text']}"  # noqa: E231,E226,E501
                )

    except Exception as e:
        print(f"\n[Execution Failed] {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
