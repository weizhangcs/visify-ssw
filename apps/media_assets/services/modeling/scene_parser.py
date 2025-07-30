# scene_parser.py
from typing import Dict, Any, Tuple

def _flatten_and_get(region_data: Dict[str, Any], key: str) -> Any:
    # ... (此函数的实现与之前版本一致)
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

def _construct_structural_metadata(region_data: Dict[str, Any]) -> Tuple[Dict, Dict, Dict]:
    # ... (此函数的实现与之前版本一致)
    branch_type = _flatten_and_get(region_data, "narrative_branch_type")
    branch_obj = None
    if branch_type == "BRANCH":
        branch_obj = {"id": _flatten_and_get(region_data, "branch_id"), "type": "multi_branch", "intersection_with": []}
    elif branch_type == "INTERSECTION":
        branch_obj = {"id": _flatten_and_get(region_data, "branch_intersection_x"), "type": "multi_branch", "intersection_with": [_flatten_and_get(region_data, "branch_intersection_y")]}
    else:
        branch_obj = {"id": 0, "type": "linear", "intersection_with": []}
    timeline_type = _flatten_and_get(region_data, "scene_timeline_marker_type")
    timeline_marker_obj, information_marker_obj = None, None
    if isinstance(timeline_type, str):
        if timeline_type in ["START", "NONE", "RETURN_PRESENT", "INSERT_PAST", "FORWARD", "PAST", "FUTURE", "UNRELATED"]:
            timeline_marker_obj = {"type": timeline_type}
            if timeline_type == "INSERT_PAST":
                timeline_marker_obj["insert_chapter_id"] = _flatten_and_get(region_data, "insert_past_chapter")
                timeline_marker_obj["insert_scene_id"] = _flatten_and_get(region_data, "insert_past_scene")
                timeline_marker_obj["inner_index"] = _flatten_and_get(region_data, "insert_past_inner_index")
            elif timeline_type in ["PAST", "FUTURE"]:
                key_prefix = timeline_type.lower()
                timeline_marker_obj["inner_index"] = _flatten_and_get(region_data, f"{key_prefix}_inner_index")
                timeline_marker_obj["extended_information"] = _flatten_and_get(region_data, f"{key_prefix}_description")
        elif timeline_type == "REFERENCE":
            information_marker_obj = {"type": "RECALL"}
    return branch_obj, timeline_marker_obj, information_marker_obj

def parse(raw_region_data: Dict[str, Any], scene_id: int, chapter_id: int) -> Dict[str, Any]:
    branch_obj, timeline_marker_obj, info_marker_obj = _construct_structural_metadata(raw_region_data)
    scene_data = {
        "id": scene_id, "name": f"Scene_{scene_id}", "textual": f"Scene {scene_id}",
        "chapter_id": chapter_id,
        "start_time_raw": raw_region_data.get("start_time"),
        "end_time_raw": raw_region_data.get("end_time"),
        "dialogues": [], "captions": [], "highlights": [], "narrative_cues": [],
        'inferred_location': _flatten_and_get(raw_region_data, 'scene_location') or 'N/A',
        'character_dynamics': _flatten_and_get(raw_region_data, 'scene_character_dynamics') or 'N/A',
        'mood_and_atmosphere': _flatten_and_get(raw_region_data, 'scene_mood_and_atmosphere') or 'N/A',
        'scene_content_type': _flatten_and_get(raw_region_data, 'scene_content_type') or 'N/A',
        "branch": branch_obj,
    }
    if timeline_marker_obj: scene_data["timeline_marker"] = timeline_marker_obj
    if info_marker_obj: scene_data["information_marker"] = info_marker_obj
    return scene_data