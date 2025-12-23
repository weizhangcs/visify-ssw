# apps/workflow/annotation/services/parsers.py

import json
import logging
import re
import uuid
from typing import Dict, List, Union

from ..schemas import (
    DataOrigin,
    DialogueContent,
    DialogueItem,
    ItemContext,
    SceneContent,
    SceneItem,
    SceneMood,
    SceneType,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Helper Functions
# ==============================================================================


def parse_time_str(time_str: str) -> float:
    """
    兼容解析时间字符串，支持 SRT (00:00:01,500) 和 ASS (0:00:01.50) 格式。
    返回秒数 (float)。
    """
    try:
        if not time_str:
            return 0.0
        # 统一处理分隔符
        time_str = time_str.replace(",", ".")
        parts = time_str.split(":")

        if len(parts) == 3:
            h, m, s = map(float, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(float, parts)
            return m * 60 + s
        return 0.0
    except Exception:
        return 0.0


def _map_enum_value(enum_cls, value: str):
    """
    [安全映射] 将字符串映射到本地 Enum 类。
    1. 尝试精确匹配。
    2. 尝试忽略大小写匹配 (例如 Cloud 返回 'Establishing'，本地定义 'establishing')。
    3. 失败返回 None。
    """
    if not value:
        return None

    # Django TextChoices 或 Python Enum 的 .values 属性
    valid_values = enum_cls.values

    # 1. 精确匹配
    if value in valid_values:
        return value

    # 2. 容错匹配
    value_lower = value.lower()
    for v in valid_values:
        if v.lower() == value_lower:
            return v

    return None


# ==============================================================================
# 1. Subtitle Parsers (ASS & SRT)
# ==============================================================================


def parse_ass_content(content: str) -> List[DialogueItem]:
    """
    解析 ASS 字幕内容。
    用于处理 CharacterAnnotationJob 的 output_ass_file。
    """
    items = []
    # ASS Format: Dialogue: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
    # Regex 捕获: Start(1), End(2), Name(3), Text(4)
    pattern = re.compile(r"Dialogue: \d+,([\d:.]+),([\d:.]+),.*?,(.*?),.*?,.*?,.*?,.*?,(.*)")

    lines = content.splitlines()
    for line in lines:
        if not line.startswith("Dialogue:"):
            continue

        match = pattern.match(line)
        if match:
            start_str, end_str, speaker_field, text_field = match.groups()

            # 清理 ASS 特效标签 (如 {\an8}, \N)
            clean_text = re.sub(r"\{.*?\}", "", text_field).strip()
            clean_text = clean_text.replace(r"\N", "\n")

            # 角色名清洗逻辑
            speaker = speaker_field.strip()
            # 如果角色名为 Default 或空，尝试从文本 "Name: Content" 中提取
            if not speaker or speaker.lower() == "default":
                if ":" in clean_text:
                    parts = clean_text.split(":", 1)
                    # 简单启发式：名字通常较短
                    if len(parts[0]) < 20:
                        speaker = parts[0].strip()
                        clean_text = parts[1].strip()
                else:
                    speaker = "Unknown"

            items.append(
                DialogueItem(
                    start=parse_time_str(start_str),
                    end=parse_time_str(end_str),
                    content=DialogueContent(text=clean_text, speaker=speaker, original_text=text_field),  # 保留原始 ASS 行内容
                    context=ItemContext(id=str(uuid.uuid4()), origin=DataOrigin.AI_ASR, is_verified=False),
                )
            )
    return items


def parse_srt_content(content: str) -> List[DialogueItem]:
    """
    解析 SRT 字幕内容。
    用于处理原始 source_subtitle 或无 ASS 输出的情况。
    """
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = content.strip().split("\n\n")
    items = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        # 确定时间轴行
        idx = 1 if "-->" in lines[1] else 0
        if "-->" not in lines[idx]:
            continue

        try:
            start_str, end_str = lines[idx].split(" --> ")
            text = "\n".join(lines[idx + 1 :])

            items.append(
                DialogueItem(
                    start=parse_time_str(start_str.strip()),
                    end=parse_time_str(end_str.strip()),
                    content=DialogueContent(text=text, speaker="Unknown"),
                    context=ItemContext(id=str(uuid.uuid4()), origin=DataOrigin.AI_ASR, is_verified=False),
                )
            )
        except Exception:
            continue
    return items


# ==============================================================================
# 2. Scene Parser (Cloud Result -> SceneItem)
# ==============================================================================


def parse_scene_json_content(data: Union[str, Dict]) -> List[SceneItem]:
    """
    [核心升级 V5.3] 解析 Cloud 端 ScenePreAnnotatorResult JSON。

    能够处理复杂的嵌套结构：
    {
        "scenes": [ { "start_slice_id": 1, "end_slice_id": 5, "narrative_action": "...", ... } ],
        "annotated_slices": [ { "slice_id": 1, "start_time": 0.0, ... } ]
    }

    映射逻辑：
    1. slice_id -> timestamp (物理定位)
    2. narrative_action -> label (标题)
    3. visual_mood_tags -> tags (保留完整列表)
    4. camera_logic, reason -> 对应字段
    """
    try:
        # 1. 数据归一化加载
        root_data = {}
        if isinstance(data, str):
            if not data.strip():
                return []
            root_data = json.loads(data)
        elif isinstance(data, dict):
            root_data = data
        else:
            logger.warning(f"Unsupported data type for scene parsing: {type(data)}")
            return []

        raw_scenes = root_data.get("scenes", [])
        raw_slices = root_data.get("annotated_slices", [])

        if not raw_scenes:
            # 如果连 scenes 都没有，可能不是预期的 Cloud 结果格式
            return []

        # 2. 构建 Slice 索引表 (Look-up Table)
        # 目的：O(1) 查找时间戳，避免 O(N*M) 的嵌套循环
        slice_map = {}
        for s in raw_slices:
            s_id = s.get("slice_id")
            if s_id is not None:
                slice_map[s_id] = s

        logger.info(f"Built index for {len(slice_map)} slices. Processing {len(raw_scenes)} scenes...")

        items = []
        for scene_def in raw_scenes:
            # -------------------------------------------------
            # A. 时间计算 (Time Resolution)
            # -------------------------------------------------
            start_id = scene_def.get("start_slice_id")
            end_id = scene_def.get("end_slice_id")

            s_slice = slice_map.get(start_id)
            e_slice = slice_map.get(end_id)

            if not s_slice:
                logger.warning(f"Scene {scene_def.get('index')} refers to missing slices IDs: {start_id}-{end_id}")
                continue

            start_time = float(s_slice.get("start_time", 0.0))

            # 2. [核心修复] 处理结束切片丢失的情况 (Clamping/Fallback)
            # TODO [Upstream Optimization]: 上游推理层需修复 LLM 对片尾 Slice ID 的幻觉问题。
            # 当前现象：LLM 倾向于在片尾生成超出范围的 end_slice_id (如实际最大2933，模型输出2997)。
            # 优化方向：1. 优化 System Prompt 增加 ID 边界约束；2. 在 Inference Service 输出前增加物理存在性校验 (Validity Check)。
            if not e_slice:
                # 这种情况通常发生在最后一个场景，LLM 幻觉了一个超出的 ID (如 2997)
                # 策略：回退使用 start_slice 的 end_time
                fallback_end_time = float(s_slice.get("end_time", 0.0))

                logger.warning(
                    f"Scene {scene_def.get('index')} refers to missing end slice ID {end_id}. "
                    f"Auto-corrected end time to slice {start_id}'s end ({fallback_end_time}s)."
                )
                end_time = fallback_end_time
            else:
                end_time = float(e_slice.get("end_time", 0.0))

            # -------------------------------------------------
            # B. 字段映射 (Rich Data Mapping)
            # -------------------------------------------------

            # 1. 标题 (Label)
            # 优先使用 narrative_action (核心事件)，兜底使用 index
            label_text = scene_def.get("narrative_action")
            if not label_text:
                label_text = f"Scene {scene_def.get('index')}"

            # 2. 枚举映射 (Type & Mood)
            safe_type = _map_enum_value(SceneType, scene_def.get("scene_type"))

            # Mood 映射策略：
            # Cloud 返回的是 tags 列表。
            # 我们保留完整列表到 tags 字段。
            # 同时也尝试提取第一个能匹配到 Local Enum 的 tag 作为 'mood' (供旧 UI 兼容)。
            cloud_tags = scene_def.get("visual_mood_tags", [])
            safe_mood = None
            if cloud_tags and isinstance(cloud_tags, list):
                for tag in cloud_tags:
                    found = _map_enum_value(SceneMood, tag)
                    if found:
                        safe_mood = found
                        break

            # 3. 构建 SceneContent
            # 此时我们假设 schemas.py 的 SceneContent 已经升级，包含下列字段
            scene_content = SceneContent(
                label=label_text,
                location=scene_def.get("primary_location", "Unknown"),
                scene_type=safe_type,
                # [Rich Data Fields]
                camera_logic=scene_def.get("camera_logic"),
                reason=scene_def.get("reason"),
                character_dynamics=scene_def.get("character_dynamics"),
                tags=cloud_tags,  # 完整 List[str]
                # 兼容旧字段
                mood=safe_mood,
                description="",  # 不再需要拼接长文本，可留空
            )

            # 4. 构建上下文
            context = ItemContext(id=str(uuid.uuid4()), origin=DataOrigin.AI_CV, is_verified=False)

            items.append(SceneItem(start=start_time, end=end_time, content=scene_content, context=context))

        return items

    except Exception as e:
        logger.error(f"Error parsing Cloud Scene data: {e}", exc_info=True)
        return []
