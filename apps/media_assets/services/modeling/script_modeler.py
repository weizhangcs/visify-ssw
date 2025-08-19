# 文件路径: apps/media_assets/services/modeling/script_modeler.py
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional

# [关键修复] 修正导入路径以适应当前项目结构
from . import ass_parser
from . import highlight_parser, narrative_cue_parser, scene_parser
from .time_utils import TimeConverter


class ScriptModeler:
    """
    (V5.1 Cleaned版)
    采用策略模式重构了Region处理逻辑，提升了可读性、扩展性和可维护性。
    此版本添加了完整的代码注释并遵循了PEP 8代码风格规范。
    """

    def __init__(self, ls_json_path: Path, project_name: str, language: str, mapping_provider: Callable[[int], Optional[Dict]]):
        """
        构造函数。
        :param ls_json_path: Label Studio 导出JSON的文件路径。
        :param project_name: 项目名称。
        :param mapping_provider: 一个外部注入的函数，用于根据全局Task ID获取映射信息。
                                 这是实现解耦的核心。
        """
        self.ls_json_path = ls_json_path
        self.project_name = project_name
        self.language = language
        self.mapping_provider = mapping_provider

        # 实例变量，用于在build方法执行期间缓存数据
        self.task_to_chapter_map: Dict[int, Dict] = {}
        self.chapter_to_ass_map: Dict[int, str] = {}
        self.temp_scenes: List[Dict] = []
        self.temp_highlights: Dict[int, List] = defaultdict(list)
        self.temp_cues: Dict[int, List] = defaultdict(list)

        # --- 处理器注册表 (Strategy Pattern的核心) ---
        self.region_handlers = {
            "SCENE": self._handle_scene,
            "HIGHLIGHT": self._handle_highlight,
            "NARRATIVE_CUE": self._handle_narrative_cue
        }

    def _handle_scene(self, data: Dict, **kwargs) -> Optional[Dict]:
        """专门处理 'SCENE' 类型的Region。"""
        scene_id_counter = kwargs['scene_id_counter']
        chapter_id = kwargs['chapter_id']
        self.temp_scenes.append(scene_parser.parse(data, scene_id_counter, chapter_id))
        return {"scene_id_counter": scene_id_counter + 1}

    def _handle_highlight(self, data: Dict, **kwargs):
        """专门处理 'HIGHLIGHT' 类型的Region。"""
        chapter_id = kwargs['chapter_id']
        self.temp_highlights[chapter_id].append(highlight_parser.parse(data))

    def _handle_narrative_cue(self, data: Dict, **kwargs):
        """专门处理 'NARRATIVE_CUE' 类型的Region。"""
        chapter_id = kwargs['chapter_id']
        self.temp_cues[chapter_id].extend(list(narrative_cue_parser.parse(data)))

    def _clean_bilingual_value(self, value: Optional[str]) -> Optional[str]:
        """
        (新增) 一个辅助方法，用于将 "中文/English" 格式的字符串，根据
        self.language 属性，清洗为纯粹的单语言值。
        """
        if not isinstance(value, str) or '/' not in value:
            return value

        try:
            chinese, english = value.split('/', 1)
            if self.language == 'zh-CN':
                return chinese
            elif self.language == 'en-US':
                return english
            else:
                return value  # 如果语言不匹配，返回原始值
        except ValueError:
            return value  # 如果格式不符，返回原始值

    def _build_project_metadata(self, scenes: Dict[str, Any], chapters: Dict[str, Any]) -> Dict[str, Any]:
        """根据场景和章节数据，构建 project_metadata 对象。"""
        return {
            "project_name": self.project_name,
            "total_chapters": len(chapters),
            "total_scenes": len(scenes),
            "version": "2.1",
            "generation_date": datetime.now(timezone.utc).isoformat()
        }

    def _build_chapters(self, scenes: Dict[str, Any]) -> Dict[str, Any]:
        """根据场景数据，构建 chapters 对象。"""
        chapters_data = defaultdict(lambda: {"scene_ids": []})
        for scene_id, scene_data in scenes.items():
            chapters_data[scene_data["chapter_id"]]["scene_ids"].append(int(scene_id))

        final_chapters = {}
        for ch_id, data in sorted(chapters_data.items()):
            ass_path = self.chapter_to_ass_map.get(ch_id, "")
            final_chapters[str(ch_id)] = {
                "id": ch_id,
                "name": f"Chapter_{ch_id}",
                "textual": f"Chapter {ch_id}",
                "source_file": Path(ass_path).name,
                "scene_ids": sorted(data["scene_ids"])
            }
        return final_chapters

    def _generate_narrative_timeline(self, scenes: Dict[str, Dict]) -> Dict[str, Any]:
        """根据所有场景的元数据，生成最终的叙事时间线。"""
        # ... (此方法的内部逻辑保持不变) ...
        scenes_by_branch = defaultdict(list)
        intersections = []
        is_linear = True

        for scene_id, scene_data in scenes.items():
            branch_info = scene_data.get('branch', {"id": 0, "type": "linear"})
            branch_id = branch_info.get("id", 0)
            scenes_by_branch[branch_id].append(scene_id)
            if branch_info.get("type") != "linear":
                is_linear = False
            if branch_info.get("intersection_with"):
                intersections.append({
                    "scene_id": int(scene_id),
                    "branches": [branch_id] + branch_info["intersection_with"]
                })

        if is_linear:
            base_timeline = [s_id for s_id, s_data in scenes.items() if
                             s_data.get("timeline_marker", {}).get("type") not in ["INSERT_PAST", "FORWARD"]]
            inserts = sorted([(s_id, s_data['timeline_marker']) for s_id, s_data in scenes.items() if
                              s_data.get("timeline_marker", {}).get("type") == "INSERT_PAST"],
                             key=lambda x: (x[1]['insert_chapter_id'], x[1]['insert_scene_id'], x[1]['inner_index']))
            for scene_to_insert_id, marker in inserts:
                target_scene_id = str(marker['insert_scene_id'])
                if target_scene_id in base_timeline:
                    base_timeline.insert(base_timeline.index(target_scene_id) + 1, scene_to_insert_id)
                else:
                    base_timeline.append(scene_to_insert_id)
            sequence = {scene_id: {"narrative_index": i + 1} for i, scene_id in enumerate(base_timeline)}
            return {"type": "linear", "sequence": sequence}

        final_branches = {}
        for branch_id, scene_ids in scenes_by_branch.items():
            branch_scenes = {s_id: scenes[s_id] for s_id in scene_ids}
            base_timeline = [s_id for s_id, s_data in branch_scenes.items() if
                             s_data.get("timeline_marker", {}).get("type") not in ["INSERT_PAST", "FORWARD"]]
            inserts = sorted([(s_id, s_data['timeline_marker']) for s_id, s_data in branch_scenes.items() if
                              s_data.get("timeline_marker", {}).get("type") == "INSERT_PAST"],
                             key=lambda x: (x[1]['insert_chapter_id'], x[1]['insert_scene_id'], x[1]['inner_index']))
            for scene_to_insert_id, marker in inserts:
                target_scene_id = str(marker['insert_scene_id'])
                if target_scene_id in base_timeline:
                    base_timeline.insert(base_timeline.index(target_scene_id) + 1, scene_to_insert_id)
                else:
                    base_timeline.append(scene_to_insert_id)
            sequence = {scene_id: {"narrative_index": i + 1} for i, scene_id in enumerate(base_timeline)}
            final_branches[f"BRANCH_{branch_id}"] = {"sequence": sequence}
        return {"type": "multi_branch", "branches": final_branches, "intersections": intersections}

    def build(self) -> Dict[str, Any]:
        """
        核心构建方法，执行从数据加载到最终JSON产物生成的完整流程。
        """
        with open(self.ls_json_path, 'r', encoding='utf-8') as f:
            all_tasks = json.load(f)

        for task in all_tasks:
            task_id = task.get("id")
            if task_id:
                mapping_info = self.mapping_provider(task_id)
                if mapping_info:
                    self.task_to_chapter_map[task_id] = mapping_info

        ass_data_cache = {}
        unique_ass_paths = {v['ass_path'] for v in self.task_to_chapter_map.values() if 'ass_path' in v}
        for path_str in unique_ass_paths:
            ass_file_path = Path(path_str)
            if ass_file_path.exists() and path_str not in ass_data_cache:
                ass_data_cache[path_str] = ass_parser.parse(ass_file_path)

        for task_id, mapping in self.task_to_chapter_map.items():
            if 'chapter_id' in mapping and 'ass_path' in mapping:
                self.chapter_to_ass_map[mapping['chapter_id']] = mapping['ass_path']

        scene_id_counter = 1
        for task_data in sorted(all_tasks, key=lambda t: t.get('id', 0)):
            task_id = task_data.get('id')
            if not task_id or task_id not in self.task_to_chapter_map:
                continue
            chapter_id = self.task_to_chapter_map[task_id]['chapter_id']

            annotation_results = task_data.get("annotations", [{}])[0].get("result", [])
            raw_regions = defaultdict(dict)
            for result in annotation_results:
                region_id, from_name, value = result.get("id"), result.get("from_name"), result.get("value")
                if not all((region_id, from_name, value)): continue
                raw_regions[region_id][from_name] = value
                if "start" in value and "end" in value:
                    raw_regions[region_id]['start_time'], raw_regions[region_id]['end_time'] = value["start"], value[
                        "end"]

            for raw_region in sorted(raw_regions.values(), key=lambda r: r.get('start_time', 0)):
                region_type_value = raw_region.get("region_type", {}).get("labels", [None])[0]
                if not region_type_value: continue
                region_type_key = (
                    region_type_value.split('/', 1)[1] if '/' in region_type_value else region_type_value).upper()

                handler = self.region_handlers.get(region_type_key)
                if handler:
                    handler_kwargs = {"chapter_id": chapter_id, "scene_id_counter": scene_id_counter}
                    updated_state = handler(raw_region, **handler_kwargs)
                    if updated_state and "scene_id_counter" in updated_state:
                        scene_id_counter = updated_state["scene_id_counter"]

        for scene_data in self.temp_scenes:
            scene_data['mood_and_atmosphere'] = self._clean_bilingual_value(scene_data.get('mood_and_atmosphere'))
            scene_data['scene_content_type'] = self._clean_bilingual_value(scene_data.get('scene_content_type'))

        for chapter_highlights in self.temp_highlights.values():
            for highlight_data in chapter_highlights:
                highlight_data['type'] = self._clean_bilingual_value(highlight_data.get('type'))
                highlight_data['mood'] = self._clean_bilingual_value(highlight_data.get('mood'))

        # 5. 聚合与“即时转换”
        project_scenes = {str(s["id"]): s for s in self.temp_scenes}
        for scene_id, scene_data in project_scenes.items():
            chapter_id = scene_data["chapter_id"]
            ass_path = self.chapter_to_ass_map.get(chapter_id)
            if not ass_path:
                continue

            # 按章节获取数据，确保数据隔离
            dialogues_in_chapter, captions_in_chapter = ass_data_cache.get(ass_path, ([], []))
            highlights_in_chapter = self.temp_highlights.get(chapter_id, [])
            cues_in_chapter = self.temp_cues.get(chapter_id, [])

            scene_start_sec = TimeConverter.ls_time_to_seconds(scene_data.get("start_time_raw"))
            scene_end_sec = TimeConverter.ls_time_to_seconds(scene_data.get("end_time_raw"))

            # 将对话（dialogue）聚合到场景中
            for dialogue in dialogues_in_chapter:
                dialogue_start_sec = TimeConverter.ass_time_to_seconds(dialogue.get("start_time_raw"))
                if scene_start_sec <= dialogue_start_sec < scene_end_sec:
                    final_dialogue = dialogue.copy()
                    final_dialogue["start_time"] = TimeConverter.seconds_to_final_format(dialogue_start_sec)
                    final_dialogue["end_time"] = TimeConverter.seconds_to_final_format(
                        TimeConverter.ass_time_to_seconds(dialogue.get("end_time_raw")))
                    del final_dialogue["start_time_raw"]
                    del final_dialogue["end_time_raw"]
                    scene_data["dialogues"].append(final_dialogue)

            # 将字幕（caption）聚合到场景中
            for caption in captions_in_chapter:
                caption_start_sec = TimeConverter.ass_time_to_seconds(caption.get("start_time_raw"))
                if scene_start_sec <= caption_start_sec < scene_end_sec:
                    final_caption = caption.copy()
                    final_caption["start_time"] = TimeConverter.seconds_to_final_format(caption_start_sec)
                    final_caption["end_time"] = TimeConverter.seconds_to_final_format(
                        TimeConverter.ass_time_to_seconds(caption.get("end_time_raw")))
                    del final_caption["start_time_raw"]
                    del final_caption["end_time_raw"]
                    scene_data["captions"].append(final_caption)

            # 将高光（highlight）聚合到场景中
            for highlight in highlights_in_chapter:
                highlight_start_sec = TimeConverter.ls_time_to_seconds(highlight.get("start_time_raw"))
                if scene_start_sec <= highlight_start_sec < scene_end_sec:
                    final_highlight = highlight.copy()
                    final_highlight["start_time"] = TimeConverter.seconds_to_final_format(highlight_start_sec)
                    final_highlight["end_time"] = TimeConverter.seconds_to_final_format(
                        TimeConverter.ls_time_to_seconds(highlight.get("end_time_raw")))
                    del final_highlight["start_time_raw"]
                    del final_highlight["end_time_raw"]
                    scene_data["highlights"].append(final_highlight)

            # 将叙事线索（narrative_cue）聚合到场景中
            for cue in cues_in_chapter:
                cue_start_sec = TimeConverter.ls_time_to_seconds(cue.get("start_time_raw"))
                if scene_start_sec <= cue_start_sec < scene_end_sec:
                    final_cue = cue.copy()
                    final_cue["start_time"] = TimeConverter.seconds_to_final_format(cue_start_sec)
                    final_cue["end_time"] = TimeConverter.seconds_to_final_format(
                        TimeConverter.ls_time_to_seconds(cue.get("end_time_raw")))
                    del final_cue["start_time_raw"]
                    del final_cue["end_time_raw"]
                    scene_data["narrative_cues"].append(final_cue)

            # 清理场景本身的原始时间戳字段
            scene_data["start_time"] = TimeConverter.seconds_to_final_format(scene_start_sec)
            scene_data["end_time"] = TimeConverter.seconds_to_final_format(scene_end_sec)
            if "start_time_raw" in scene_data:
                del scene_data["start_time_raw"]
            if "end_time_raw" in scene_data:
                del scene_data["end_time_raw"]

        # 6. 构建并返回最终的完整JSON结构
        chapters = self._build_chapters(project_scenes)
        project_metadata = self._build_project_metadata(project_scenes, chapters)
        narrative_timeline = self._generate_narrative_timeline(project_scenes)

        return {
            "project_metadata": project_metadata,
            "chapters": chapters,
            "scenes": project_scenes,
            "narrative_timeline": narrative_timeline
        }