import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

# 假设我们之前开发的解析器现在是可导入的模块
# 并且annotation_parser.py中的主函数已重命名为parse_label_studio_export
# 为保持独立性，此处暂时将ASS解析逻辑直接放入


from apps.media_assets.services.modeling import ass_parser, scene_parser, highlight_parser, narrative_cue_parser
from apps.media_assets.services.modeling.time_utils import TimeConverter


class ScriptModeler:
    """
    总编排器，负责将Label Studio的JSON标注和Aegisub的ASS文件
    完全整合成最终的 structured_script.json。
    """

    def __init__(self, ls_json_path: Path, ass_dir_path: Path):
        self.ls_json_path = ls_json_path
        self.ass_dir_path = ass_dir_path
        self.project_name = ass_dir_path.name

    def _build_project_metadata(self, scenes: Dict[str, Any], chapters: Dict[str, Any]) -> Dict[str, Any]:
        """根据场景和章节数据，构建 project_metadata 对象。"""
        return {
            "project_name": self.project_name,  # [cite: 196]
            "total_chapters": len(chapters),  # [cite: 196]
            "total_scenes": len(scenes),  # [cite: 196]
            "version": "1.8",  # 根据元数据规范v1.9，版本号恒为"1.8" [cite: 196]
            "generation_date": datetime.now(timezone.utc).isoformat()  # [cite: 196]
        }

    def _build_chapters(self, scenes: Dict[str, Any]) -> Dict[str, Any]:
        """根据场景数据，构建 chapters 对象。"""
        chapters_data = defaultdict(lambda: {"scene_ids": []})

        # 按 chapter_id 分组
        for scene_id, scene_data in scenes.items():
            chapter_id = scene_data["chapter_id"]
            chapters_data[chapter_id]["scene_ids"].append(int(scene_id))

        # 格式化输出
        final_chapters = {}
        for ch_id, data in sorted(chapters_data.items()):
            final_chapters[str(ch_id)] = {
                "id": ch_id,  # [cite: 199]
                "name": f"Chapter_{ch_id}",  # [cite: 199]
                "textual": f"Chapter {ch_id}",  # [cite: 199]
                "source_file": f"{str(ch_id).zfill(2)}.ass",  # [cite: 199]
                "scene_ids": sorted(data["scene_ids"])  # [cite: 199]
            }
        return final_chapters

    def _generate_narrative_timeline(self, scenes: Dict[str, Dict]) -> Dict[str, Any]:
        """根据所有场景的元数据，生成最终的叙事时间线。"""
        # 1. 按分支ID对所有场景进行分组
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

        # 如果所有场景都是线性，则使用简单逻辑
        if is_linear:
            base_timeline = [s_id for s_id, s_data in scenes.items() if
                             s_data.get("timeline_marker", {}).get("type") not in ["INSERT_PAST", "FORWARD"]]
            inserts = sorted([(s_id, s_data['timeline_marker']) for s_id, s_data in scenes.items() if
                              s_data.get("timeline_marker", {}).get("type") == "INSERT_PAST"],
                             key=lambda x: (x[1]['insert_chapter_id'], x[1]['insert_scene_id'], x[1]['inner_index']))
            for scene_to_insert_id, marker in inserts:
                target_scene_id = str(marker['insert_scene_id'])
                if target_scene_id in base_timeline:
                    insert_index = base_timeline.index(target_scene_id) + 1
                    base_timeline.insert(insert_index, scene_to_insert_id)
                else:
                    base_timeline.append(scene_to_insert_id)
            sequence = {scene_id: {"narrative_index": i + 1} for i, scene_id in enumerate(base_timeline)}
            return {"type": "linear", "sequence": sequence}

        # --- 多分支叙事排序逻辑 ---
        final_branches = {}
        for branch_id, scene_ids in scenes_by_branch.items():
            branch_scenes = {s_id: scenes[s_id] for s_id in scene_ids}

            # 对每个分支，独立应用线性排序逻辑
            base_timeline = [s_id for s_id, s_data in branch_scenes.items() if
                             s_data.get("timeline_marker", {}).get("type") not in ["INSERT_PAST", "FORWARD"]]
            inserts = sorted([(s_id, s_data['timeline_marker']) for s_id, s_data in branch_scenes.items() if
                              s_data.get("timeline_marker", {}).get("type") == "INSERT_PAST"],
                             key=lambda x: (x[1]['insert_chapter_id'], x[1]['insert_scene_id'], x[1]['inner_index']))

            for scene_to_insert_id, marker in inserts:
                target_scene_id = str(marker['insert_scene_id'])
                if target_scene_id in base_timeline:
                    insert_index = base_timeline.index(target_scene_id) + 1
                    base_timeline.insert(insert_index, scene_to_insert_id)
                else:
                    base_timeline.append(scene_to_insert_id)

            sequence = {scene_id: {"narrative_index": i + 1} for i, scene_id in enumerate(base_timeline)}
            final_branches[f"BRANCH_{branch_id}"] = {"sequence": sequence}

        # [FIX] 修复：根据规范，返回完整的 narrative_timeline 对象
        return {
            "type": "multi_branch",  #
            "branches": final_branches,  #
            "intersections": intersections  #
        }

    def build(self) -> Dict[str, Any]:
        # 1. 加载源文件
        with open(self.ls_json_path, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)

        all_tasks = loaded_data if isinstance(loaded_data, list) else []

        # 2. 预处理：解析所有ASS文件
        ass_data_cache = {}
        for task_data in all_tasks:
            file_upload = task_data.get("file_upload", "")
            if not file_upload: continue
            match = re.search(r'ep(\d+)', file_upload)
            if not match: continue

            chapter_number_str = match.group(1).zfill(2)
            ass_filename = f"{chapter_number_str}.ass"
            if ass_filename not in ass_data_cache:
                ass_file_path = self.ass_dir_path / ass_filename
                if ass_file_path.exists():
                    ass_data_cache[ass_filename] = ass_parser.parse(ass_file_path)
                else:
                    ass_data_cache[ass_filename] = ([], [])

        # 3. 预处理：解析所有Label Studio标注
        temp_scenes, temp_highlights, temp_cues = [], [], []
        scene_id_counter = 1
        for task_data in sorted(all_tasks, key=lambda t: t.get('inner_id', 0)):
            chapter_id_match = re.search(r'ep(\d+)', task_data.get("file_upload", ""))
            if not chapter_id_match: continue
            chapter_id = int(chapter_id_match.group(1))

            annotation_results = task_data.get("annotations", [{}])[0].get("result", [])
            raw_regions = defaultdict(dict)
            for result in annotation_results:
                region_id = result.get("id")
                from_name, value = result.get("from_name"), result.get("value")
                if not region_id or not from_name or not value: continue
                raw_regions[region_id][from_name] = value
                if "start" in value and "end" in value:
                    raw_regions[region_id]['start_time'] = value["start"]
                    raw_regions[region_id]['end_time'] = value["end"]

            for raw_region in sorted(raw_regions.values(), key=lambda r: r.get('start_time', 0)):
                region_type_value = raw_region.get("region_type", {}).get("labels", [None])[0]
                if not region_type_value: continue
                region_type_key = (
                    region_type_value.split('/', 1)[1] if '/' in region_type_value else region_type_value).upper()

                if region_type_key == "SCENE":
                    temp_scenes.append(scene_parser.parse(raw_region, scene_id_counter, chapter_id))
                    scene_id_counter += 1
                elif region_type_key == "HIGHLIGHT":
                    temp_highlights.append(highlight_parser.parse(raw_region))
                elif region_type_key == "NARRATIVE_CUE":
                    temp_cues.extend(list(narrative_cue_parser.parse(raw_region)))

        # 4. 组装与“即时转换”
        project_scenes = {str(s["id"]): s for s in temp_scenes}
        for scene_id, scene_data in project_scenes.items():
            chapter_id = scene_data["chapter_id"]
            ass_filename = f"{str(chapter_id).zfill(2)}.ass"
            dialogues_in_chapter, captions_in_chapter = ass_data_cache.get(ass_filename, ([], []))

            scene_start_sec = TimeConverter.ls_time_to_seconds(scene_data.get("start_time_raw"))
            scene_end_sec = TimeConverter.ls_time_to_seconds(scene_data.get("end_time_raw"))

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

            for highlight in temp_highlights:
                highlight_start_sec = TimeConverter.ls_time_to_seconds(highlight.get("start_time_raw"))
                if scene_start_sec <= highlight_start_sec < scene_end_sec:
                    final_highlight = highlight.copy()
                    final_highlight["start_time"] = TimeConverter.seconds_to_final_format(highlight_start_sec)
                    final_highlight["end_time"] = TimeConverter.seconds_to_final_format(
                        TimeConverter.ls_time_to_seconds(highlight.get("end_time_raw")))
                    del final_highlight["start_time_raw"]
                    del final_highlight["end_time_raw"]
                    scene_data["highlights"].append(final_highlight)

            for cue in temp_cues:
                cue_start_sec = TimeConverter.ls_time_to_seconds(cue.get("start_time_raw"))
                if scene_start_sec <= cue_start_sec < scene_end_sec:
                    final_cue = cue.copy()
                    final_cue["start_time"] = TimeConverter.seconds_to_final_format(cue_start_sec)
                    final_cue["end_time"] = TimeConverter.seconds_to_final_format(
                        TimeConverter.ls_time_to_seconds(cue.get("end_time_raw")))
                    del final_cue["start_time_raw"]
                    del final_cue["end_time_raw"]
                    scene_data["narrative_cues"].append(final_cue)

            scene_data["start_time"] = TimeConverter.seconds_to_final_format(scene_start_sec)
            scene_data["end_time"] = TimeConverter.seconds_to_final_format(scene_end_sec)
            if "start_time_raw" in scene_data: del scene_data["start_time_raw"]
            if "end_time_raw" in scene_data: del scene_data["end_time_raw"]

        # 5. 构建最终输出
        chapters = self._build_chapters(project_scenes)
        project_metadata = self._build_project_metadata(project_scenes, chapters)
        narrative_timeline = self._generate_narrative_timeline(project_scenes)

        return {
            "project_metadata": project_metadata,
            "chapters": chapters,
            "scenes": project_scenes,
            "narrative_timeline": narrative_timeline
        }


# --- 使用示例 ---
if __name__ == '__main__':
    # 假设所有相关py文件都在同一目录下
    # 设定输入文件和目录
    LS_JSON_FILE = Path(r"C:\Users\wei_z\Downloads\project-23-at-2025-07-22-06-45-75709e10.json")
    ASS_DIR = Path(r"D:\DevProjects\PyCharmProjects\visify-ae\input\AFlashMarriageWithTheBillionaireTycoon\v3_merged")  # 假设ASS文件都存放在这个文件夹

    # 初始化并运行总编排器
    modeler = ScriptModeler(ls_json_path=LS_JSON_FILE, ass_dir_path=ASS_DIR)
    final_structured_script = modeler.build()

    # 将结果保存到文件
    output_filename = Path(r"D:\DevProjects\PyCharmProjects\visify-ae\debug\test_outputs\modeling\pased_label_studio_output.json")
    output_filename.parent.mkdir(exist_ok=True)
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(final_structured_script, f, indent=2, ensure_ascii=False)

    print(f"最终脚本已生成: '{output_filename}'")