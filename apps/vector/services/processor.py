# 文件路径: apps/vector/services/processor.py

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from apps.common.schemas.dataset.schemas import Scene, Slice, SubtitleItem, VisualAnalysis

logger = logging.getLogger(__name__)


class DataProcessorService:
    """
    [Production Craft] 数据预处理工艺。
    负责将异构的业务数据 (Dict) 转化为适合向量化的语义文本 (Text)。

    [Data Governance]
    采用 Metadata 驱动的设计。
    - 标签定义在 apps/vector/metadata/*.json 中。
    - 支持多语言配置。
    - 使用类级缓存避免频繁 I/O。
    """

    # 单例缓存: {index_type: {lang: config_dict}}
    _config_cache = {}
    _METADATA_DIR = Path(__file__).resolve().parent.parent / "metadata"

    @classmethod
    def _get_config(cls, index_type: str, lang: str = "zh") -> Dict[str, Any]:
        """加载并缓存配置"""
        if index_type not in cls._config_cache:
            config_path = cls._METADATA_DIR / f"{index_type}.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    cls._config_cache[index_type] = json.load(f)
            else:
                cls._config_cache[index_type] = {}

        return cls._config_cache[index_type].get(lang, {})

    @classmethod
    def extract_text(cls, item: Dict, index_type: str) -> Optional[str]:
        """
        根据索引类型分发提取逻辑。
        """
        extractor = getattr(cls, f"_extract_{index_type}", None)
        if extractor:
            return extractor(item)
        return None

    @staticmethod
    def _extract_dialogue(item: Dict) -> str:
        # [SSOT] 强制转换为 Pydantic 对象
        try:
            obj = SubtitleItem(**item)
        except Exception as e:
            logger.warning(f"Dialogue validation failed: {e}")
            return ""

        config = DataProcessorService._get_config("dialogue")
        sep = config.get("separator", "：")

        if not obj.content:
            return ""
        return f"{obj.speaker}{sep}{obj.content}"

    @staticmethod
    def _extract_scene(item: Dict) -> str:
        # [Compatibility] 兼容旧数据：如果 scene_type 是字符串，临时修正为 LabelValue 结构
        # 以便通过 Pydantic 校验
        content_dict = item.get("content", {})
        if isinstance(content_dict, dict):
            st = content_dict.get("scene_type")
            if isinstance(st, str):
                # 这是一个临时补丁，防止旧数据导致索引构建失败
                item = item.copy()
                item["content"] = content_dict.copy()
                item["content"]["scene_type"] = {"value": st, "label": st}

        # [SSOT] 强制转换为 Pydantic 对象
        try:
            scene_obj = Scene(**item)
        except Exception as e:
            logger.warning(f"Scene validation failed: {e}")
            return ""

        config = DataProcessorService._get_config("scene")
        sep = config.get("separator", "；")
        kv_sep = config.get("kv_separator", "：")

        content = scene_obj.content
        parts = []

        # 核心剧情
        if content.narrative_action:
            label = config.get("narrative_action", "剧情")
            parts.append(f"{label}{kv_sep}{content.narrative_action}")

        # 环境信息
        if content.location:
            label = config.get("location", "地点")
            parts.append(f"{label}{kv_sep}{content.location}")

        # [新增] 场景类型 (支持 LabelValue 结构或字符串)
        scene_type = content.scene_type
        if scene_type:
            label = config.get("scene_type", "类型")
            # Pydantic 对象属性访问
            val = scene_type.label or scene_type.value
            if val and val.lower() != "unknown":
                parts.append(f"{label}{kv_sep}{val}")

        # [新增] 运镜逻辑
        if content.camera_logic:
            label = config.get("camera_logic", "运镜")
            parts.append(f"{label}{kv_sep}{content.camera_logic}")

        # [新增] 角色关系
        if content.character_dynamics:
            label = config.get("character_dynamics", "关系")
            parts.append(f"{label}{kv_sep}{content.character_dynamics}")

        # 氛围标签
        if content.visual_mood_tags:
            label = config.get("visual_mood_tags", "氛围")
            parts.append(f"{label}{kv_sep}{'、'.join(content.visual_mood_tags)}")

        return sep.join(parts)

    @staticmethod
    def _extract_slice(item: Dict) -> str:
        config = DataProcessorService._get_config("slice")
        sep = config.get("separator", "；")
        kv_sep = config.get("kv_separator", "：")

        # [Re-hydration] 尝试恢复 Pydantic 对象
        # [Fix] 兼容性处理：如果 type 退化为字符串 (e.g. "visual_segment")
        if isinstance(item.get("type"), str):
            val = item["type"]
            item = item.copy()
            item["type"] = {"value": val, "label": val}

        try:
            slice_obj = Slice(**item)
        except Exception as e:
            logger.warning(f"Slice validation failed: {e}")
            return ""

        parts = []

        # 1. 类型 (Type)
        if slice_obj.type:
            label = config.get("type", "类型")
            val = slice_obj.type.label or slice_obj.type.value
            parts.append(f"{label}{kv_sep}{val}")

        analysis = slice_obj.slice_analysis
        if analysis:
            # 2. 画面 (Visual)
            if analysis.visual_summary:
                label = config.get("visual_summary", "画面")
                parts.append(f"{label}{kv_sep}{analysis.visual_summary}")

            # 3. 剧情 (Narrative)
            if analysis.narrative_summary:
                label = config.get("narrative_summary", "剧情")
                parts.append(f"{label}{kv_sep}{analysis.narrative_summary}")

            # 4. 标签 (Tags)
            if analysis.tags:
                label = config.get("tags", "标签")
                parts.append(f"{label}{kv_sep}{'、'.join(analysis.tags)}")

        return sep.join(parts)

    @staticmethod
    def _extract_frame(item: Dict) -> str:
        config = DataProcessorService._get_config("frame")
        sep = config.get("separator", "；")
        kv_sep = config.get("kv_separator", "：")

        raw_va = item.get("visual_analysis") or {}

        # [Re-hydration] 尝试恢复 Pydantic 对象
        # [Fix] 兼容性处理：如果 shot_type 退化为字符串
        if isinstance(raw_va.get("shot_type"), str):
            val = raw_va["shot_type"]
            raw_va = raw_va.copy()
            raw_va["shot_type"] = {"value": val, "label": val}

        try:
            va_obj = VisualAnalysis(**raw_va)
        except Exception as e:
            logger.warning(f"Frame validation failed: {e}")
            return ""

        parts = []

        if va_obj.subject:
            label = config.get("subject", "主体")
            parts.append(f"{label}{kv_sep}{va_obj.subject}")

        if va_obj.action:
            label = config.get("action", "动作")
            parts.append(f"{label}{kv_sep}{va_obj.action}")

        if va_obj.environment:
            label = config.get("environment", "环境")
            parts.append(f"{label}{kv_sep}{va_obj.environment}")

        # 补充其他字段 (Shot, Lighting, Mood)
        if va_obj.shot_type:
            label = config.get("shot_type", "景别")
            val = va_obj.shot_type.label or va_obj.shot_type.value
            parts.append(f"{label}{kv_sep}{val}")

        if va_obj.lighting_time:
            label = config.get("lighting_time", "光影")
            parts.append(f"{label}{kv_sep}{va_obj.lighting_time}")

        if va_obj.visual_mood_tags:
            label = config.get("visual_mood_tags", "氛围")
            parts.append(f"{label}{kv_sep}{'、'.join(va_obj.visual_mood_tags)}")

        return sep.join(parts)
