# ass_parser.py

from pathlib import Path
from typing import Dict, List, Tuple
import json

# 导入我们新建的公共工具
# from time_utils import TimeConverter


def parse(ass_file_path: Path) -> Tuple[List[Dict], List[Dict]]:
    """
    接收一个.ass文件路径，将其解析为dialogues和captions列表。
    只输出包含原始时间字符串的中间数据对象。
    """
    if not ass_file_path.exists():
        print(f"Warning: ASS file not found at {ass_file_path}")
        return [], []

    dialogues, captions = [], []
    with open(ass_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    event_section = False
    for line in lines:
        line = line.strip()
        if line.lower() == '[events]': event_section = True; continue
        if event_section and line.startswith('['): break
        if not event_section or not line.lower().startswith('dialogue:'): continue

        parts = line.split(':', 1)[1].strip().split(',', 9)
        if len(parts) < 10: continue

        start_time_str, end_time_str, name, text = parts[1], parts[2], parts[4], parts[9]
        event_data = {
            "start_time_raw": start_time_str,
            "end_time_raw": end_time_str,
            "content": text.replace('\\N', '\n')
        }
        if name.upper() == 'CAPTION':
            captions.append(event_data)
        else:
            event_data["speaker"] = name
            dialogues.append(event_data)
    return dialogues, captions


# --- 独立测试入口 ---
if __name__ == '__main__':
    # 设定要测试的ASS文件路径
    # 请将此路径替换为您的真实文件路径
    ASS_FILE_TO_TEST = Path(r"D:\DevProjects\PyCharmProjects\visify-ae\input\ShesBack\v3_merged_v2\01.ass")

    print(f"--- [DEBUG] Parsing ASS file: {ASS_FILE_TO_TEST.name} ---")

    # 调用解析函数
    parsed_dialogues, parsed_captions = parse(ASS_FILE_TO_TEST)

    # 将结果打包到一个字典中，便于查看
    output_data = {
        "dialogues": parsed_dialogues,
        "captions": parsed_captions
    }

    # 定义输出文件，并确保目录存在
    output_dir = Path("debug")
    output_dir.mkdir(exist_ok=True)
    output_filename = output_dir / f"{ASS_FILE_TO_TEST.stem}_parsed.json"

    # 将解析结果写入JSON文件，以便详细检查
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"--- [SUCCESS] ---")
    print(f"Total Dialogues Parsed: {len(parsed_dialogues)}")
    print(f"Total Captions Parsed: {len(parsed_captions)}")
    print(f"Results saved to: '{output_filename}'")