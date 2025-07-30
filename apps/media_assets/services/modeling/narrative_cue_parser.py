# narrative_cue_parser.py (修订版)

from typing import Dict, Any, Iterator

def parse(raw_region_data: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """
    解析一个“叙事线索”区域，为多行输入生成多个中间对象。
    只输出包含原始浮点数时间的中间对象。
    """
    # 检查是否存在“关键信息”
    key_info_values = raw_region_data.get("key_information_summary", {}).get("text", [])
    if key_info_values:
        for text_value in key_info_values:
            if not text_value: continue
            yield {
                "start_time_raw": raw_region_data.get("start_time"),
                "end_time_raw": raw_region_data.get("end_time"),
                "type": "Key_Information",
                "value": text_value  # [FIX] "summary" 已修改为 "value"
            }

    # 检查是否存在“物品”
    object_names = raw_region_data.get("object_name", {}).get("text", [])
    if object_names:
        for text_value in object_names:
            if not text_value: continue
            yield {
                "start_time_raw": raw_region_data.get("start_time"),
                "end_time_raw": raw_region_data.get("end_time"),
                "type": "Object",
                "value": text_value  # [FIX] "summary" 已修改为 "value"
            }