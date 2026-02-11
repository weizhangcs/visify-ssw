"""
使用说明 (Usage):
   docker compose -p vss-edge -f docker-compose.base.yml -f docker-compose.dev.yml
   run --rm worker-media python tests/atomflow/dubbing/test_gating_service.py
   注意: 请确保 input_audio_path 文件存在，且代码目录已挂载到容器中。
"""
import os
import sys
import time
from pathlib import Path

import torch

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
# os.environ["YAMNET_MODEL_PATH"] = r"D:\Models\yamnet\yamnet.onnx"
# os.environ["VAD_MODEL_PATH"] = r"D:\Models\vad\silero_vad.onnx"

# --- 3. 导入服务 ---
try:
    from apps.atomflow.dubbing import constants
    from apps.atomflow.dubbing.services.gating import AudioGatingService, GatingConfig
except ImportError as e:
    print(f"[Error] Import failed: {e}")
    print("请确保项目根目录已正确添加到 PYTHONPATH。")
    sys.exit(1)


def main():
    print("=" * 50)
    print("   AudioGatingService Manual Test")
    print("=" * 50)

    # --- 4. 准备输入输出 ---
    # [配置] 请确保这里指向一个真实存在的 WAV 文件
    # 建议在 tests/resources 下放一个 test_vocals.wav
    input_audio_path = (
        project_root
        / "media_root/dubbing/3d30b544-fd12-4f65-9000-3216b9984ad6/EP01_(Vocals)_model_bs_roformer_ep_317_sdr_12.wav"
    )

    # 输出目录
    output_base = project_root / "tests/testdata/output/dubbing"
    output_base.mkdir(parents=True, exist_ok=True)

    print(f"Input Audio: {input_audio_path}")
    print(f"Output Dir:  {output_base}")  # noqa: E241
    print(f"Model (YAMNet): {constants.YAMNET_MODEL_PATH}")
    print(f"Model (VAD):    {constants.VAD_MODEL_PATH}")  # noqa: E241

    if not input_audio_path.exists():
        print(f"\n[Error] 文件不存在: {input_audio_path}")
        print("请修改脚本中的 input_audio_path 变量，指向一个有效的音频文件。")
        # 尝试创建目录方便用户放置文件
        input_audio_path.parent.mkdir(parents=True, exist_ok=True)
        return

    # --- 5. [可选] 自定义配置 ---
    # 创建一个配置实例，可以覆盖默认值以进行调优
    # 例如，让 VAD 对语音更敏感一些
    custom_config = GatingConfig(perception_vad_threshold=0.18, material_vad_threshold=0.12)  # 默认是 0.20  # 默认是 0.15
    print("\n[Config] Using custom configuration for this run.")

    # --- 6. 执行调用 ---
    try:
        print("\n>>> Starting Service Execution...")
        start_time = time.time()
        print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")

        # 直接调用静态方法 run
        result = AudioGatingService.run(
            vocals_path=str(input_audio_path), output_base=output_base, config=custom_config
        )

        end_time = time.time()
        duration = end_time - start_time

        print("\n>>> Execution Successful!")
        print(f"End Time:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")  # noqa: E241
        print(f"Duration:   {duration:.2f} seconds")  # noqa: E241,E231
        print(f"Result: {result}")

        # --- 7. 简单验证结果 ---
        mask_path = result.get("mask_path")
        if mask_path and os.path.exists(mask_path):
            print(f"\n[Verification] Loading generated masks from: {mask_path}")
            # 使用 weights_only=True 更安全，且能抑制 PyTorch 警告
            masks = torch.load(mask_path, weights_only=True)
            print(f"Keys found: {list(masks.keys())}")
            for k, v in masks.items():
                if isinstance(v, torch.Tensor):
                    print(f" - {k}: Shape {v.shape}, Type {v.dtype}")

            # --- 8. 后处理：生成验证音频 ---
            print("\n[Post-processing] Generating verification audio files...")
            try:
                import torchaudio

                # 加载原始音频
                audio, sr = torchaudio.load(input_audio_path)

                # [关键] 确保音频与掩码的采样率一致
                # Gating Service 内部统一使用 16kHz 处理，因此这里也需要对齐
                target_sr = 16000
                if sr != target_sr:
                    print(
                        f"\n[Post-processing] Resampling audio from {sr}Hz to {target_sr}Hz to match mask's sample rate..."  # noqa: E501
                    )
                    resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=target_sr)
                    audio = resampler(audio)
                    # 更新采样率变量以供 torchaudio.save 使用
                    sr = target_sr

                # 确保 mask 和 audio 在同一设备上
                device = audio.device
                perception_mask = masks.get("perception").to(device)
                material_mask = masks.get("material").to(device)

                # 检查并对齐长度
                min_len = min(audio.shape[1], perception_mask.shape[0], material_mask.shape[0])
                audio = audio[:, :min_len]
                perception_mask = perception_mask[:min_len]
                material_mask = material_mask[:min_len]

                # 应用掩码 (unsqueeze(0) to allow broadcasting across channels)
                speech_only_audio = audio * perception_mask.unsqueeze(0)
                # 1.0 - perception: 被感知掩码剔除的内容（包含音乐、强噪音等）
                non_speech_audio = audio * (1.0 - perception_mask.unsqueeze(0))
                # material: 将要回填到背景轨的内容（纯环境音/静音）
                backfill_audio = audio * material_mask.unsqueeze(0)

                # 保存音频
                speech_output_path = output_base / "gating_speech_only.wav"  # 纯净的人声对白（用于ASR/TTS）
                non_speech_output_path = output_base / "gating_non_speech.wav"  # 不是说话的所有东西（可能包括背景音乐/歌唱/突兀噪音 ）
                backfill_output_path = output_base / "gating_backfill_preview.wav"  # 纯背景音的底噪

                torchaudio.save(speech_output_path, speech_only_audio, sr)
                torchaudio.save(non_speech_output_path, non_speech_audio, sr)
                torchaudio.save(backfill_output_path, backfill_audio, sr)

                print(f" - Speech-only audio saved to: {speech_output_path}")
                print(f" - Non-speech audio saved to: {non_speech_output_path}")
                print(f" - Backfill preview saved to: {backfill_output_path}")

            except ImportError:
                print("\n[Warning] torchaudio is not installed. Skipping audio generation.")
            except Exception as e:
                print(f"\n[Error] Failed to generate verification audio: {e}")

    except Exception as e:
        print(f"\n[Execution Failed] {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
