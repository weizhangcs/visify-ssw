"""
使用说明 (Usage):
   docker compose -p vss-edge -f docker-compose.base.yml -f docker-compose.dev.yml
   run --rm worker-media python tests/atomflow/dubbing/test_character_service.py
   注意: 此测试需要网络连接以访问 VSS Cloud API。
"""
import json
import os
import sys
import time
from pathlib import Path

import django

# --- 1. 环境引导 (Bootstrap) ---
current_file = Path(__file__).resolve()
project_root = current_file.parent
while not (project_root / "apps").exists() and project_root != project_root.parent:
    project_root = project_root.parent

if str(project_root) not in sys.path:
    print(f"Adding project root to sys.path: {project_root}")
    sys.path.insert(0, str(project_root))

# --- 1.1 Django 环境初始化 ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "visify_ssw.settings")
django.setup()

# --- 2. 导入服务 ---
try:
    from apps.atomflow.dubbing.services.character import CharacterRoleFinalizerService
except ImportError as e:
    print(f"[Error] Import failed: {e}")
    sys.exit(1)


def format_srt_timestamp(seconds: float) -> str:
    """将秒数转换为 SRT 时间戳格式 (HH:MM:SS,ms)。"""
    if seconds is None:
        seconds = 0.0

    total_seconds = int(seconds)
    milliseconds = int(round((seconds - total_seconds) * 1000))

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"  # noqa: E231


def convert_to_srt(metadata_path: Path, output_srt_path: Path):
    """将最终的 metadata.json 转换为包含角色名的 SRT 字幕文件。"""
    print(f"\n[Post-processing] Converting {metadata_path.name} to SRT...")

    if not metadata_path.exists():
        print(f"[Error] Metadata file not found: {metadata_path}")
        return

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    srt_blocks = []
    for i, seg in enumerate(metadata):
        start_time = format_srt_timestamp(seg.get("start", 0.0))
        end_time = format_srt_timestamp(seg.get("end", 0.0))

        character = seg.get("character", "UNKNOWN")
        text = seg.get("refined_text", "")

        content = f"{character}: {text}"

        block = f"{i + 1}\n{start_time} --> {end_time}\n{content}\n"
        srt_blocks.append(block)

    with open(output_srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_blocks))

    print(f"SRT file saved to: {output_srt_path}")


def main():
    print("=" * 50)
    print("   CharacterRoleFinalizerService Manual Test")
    print("=" * 50)

    # --- 3. 准备输入 ---
    test_data_dir = project_root / "tests" / "testdata" / "output" / "dubbing"
    fusion_json_path = test_data_dir / "fusion_result.json"

    if fusion_json_path.exists():
        print(f"[Info] Loading real Fusion data from: {fusion_json_path}")
        with open(fusion_json_path, "r", encoding="utf-8") as f:
            fusion_data = json.load(f)
    else:
        print("[Info] Real Fusion data not found. Using mock data.")
        # 模拟 Fusion 产出，包含物理 ID 和置信度
        fusion_data = [
            {"start": 6.4, "end": 7.0, "refined_text": "我是安然。", "speaker": "PERSON_00", "fusion_score": 0.95},
            {"start": 7.5, "end": 9.0, "refined_text": "安总，您好。", "speaker": "PERSON_01", "fusion_score": 0.88},
            {
                "start": 9.5,
                "end": 10.5,
                "refined_text": "不用客气。",
                "speaker": "PERSON_00",  # 物理层正确识别
                "fusion_score": 0.92,
            },
            {
                "start": 11.0,
                "end": 12.0,
                "refined_text": "好的，安然小姐。",
                "speaker": "PERSON_02",  # 物理层可能误判，或者是第三人
                "fusion_score": 0.40,  # 低置信度，期待 LLM 修正或确认
            },
        ]

    # 输出路径
    output_base = project_root / "tests/testdata/output/dubbing"
    output_base.mkdir(parents=True, exist_ok=True)
    output_json_path = output_base / "character_finalization_result.json"

    print(f"Input Segments: {len(fusion_data)}")
    print(f"Output JSON: {output_json_path}")

    # --- 4. 执行调用 ---
    try:
        print("\n>>> Starting Service Execution...")
        start_time = time.time()

        # 调用服务
        result = CharacterRoleFinalizerService.run(fusion_data=fusion_data, lang="zh")

        end_time = time.time()
        duration = end_time - start_time

        print("\n>>> Execution Successful!")
        print(f"Duration: {duration:.2f} seconds")  # noqa: E231

        # --- 5. 验证与保存 ---
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Result saved to: {output_json_path}")

        finalized_script = result.get("finalized_script", [])
        character_map = result.get("character_map", [])

        print(f"\n[Verification] Finalized {len(finalized_script)} segments.")
        print(f"[Verification] Identified {len(character_map)} characters.")
        print(f"Character Map: {json.dumps(character_map, ensure_ascii=False, indent=2)}")

        # --- 6. 回填角色名并导出 metadata.json ---
        # 将识别到的角色名回填到原始的 fusion_data 中，形成最终的 metadata.json
        if len(finalized_script) == len(fusion_data):
            print("\n[Post-processing] Backfilling character names to metadata...")
            for i, seg in enumerate(finalized_script):
                # 回填角色名
                if "character_name" in seg:
                    fusion_data[i]["character"] = seg["character_name"]
                # 回填修正后的 speaker_id (如果有)
                if "speaker_id" in seg:
                    fusion_data[i]["speaker"] = seg["speaker_id"]

            metadata_path = output_base / "metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(fusion_data, f, ensure_ascii=False, indent=2)
            print(f"Metadata (Fusion + Character Names) saved to: {metadata_path}")

            # --- 7. 导出 SRT 字幕 ---
            srt_path = output_base / "metadata.srt"
            convert_to_srt(metadata_path, srt_path)
        else:
            print(
                f"\n[Warning] Segment count mismatch (Input: {len(fusion_data)}, Output: {len(finalized_script)}). Skipping metadata backfill."  # noqa: E501
            )

    except Exception as e:
        print(f"\n[Execution Failed] {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
