# highlight_parser.py
from typing import Dict, Any

def _flatten_and_get(region_data: Dict[str, Any], key: str) -> Any:
    """一个安全的取值函数，能处理嵌套的Label Studio值对象。"""
    if key in region_data:
        value_obj = region_data[key]
        if isinstance(value_obj, dict):
            if "choices" in value_obj: value_to_store = value_obj["choices"][0]
            elif "text" in value_obj: value_to_store = value_obj["text"][0]
            elif "number" in value_obj: return value_obj["number"]
            else: return None
            if isinstance(value_to_store, str) and '/' in value_to_store:
                return value_to_store.split('/', 1)[1]
            return value_to_store
    return None

def parse(raw_region_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    解析一个“高光”区域，只输出包含原始浮点数时间的中间对象。
    """
    return {
        "start_time_raw": raw_region_data.get("start_time"),
        "end_time_raw": raw_region_data.get("end_time"),
        "id": _flatten_and_get(raw_region_data, "highlight_id"),
        "type": _flatten_and_get(raw_region_data, "highlight_type"),
        "description": _flatten_and_get(raw_region_data, "highlight_description"),
        "mood": _flatten_and_get(raw_region_data, "highlight_mood")
    }