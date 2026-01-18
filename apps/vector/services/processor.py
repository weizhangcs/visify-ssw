# 文件路径: apps/vector/services/processor.py

import json
from pathlib import Path
from typing import Any, Dict, Optional


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
        config = DataProcessorService._get_config("dialogue")
        sep = config.get("separator", "：")

        speaker = item.get("speaker", "Unknown")
        content = item.get("content", "")
        if not content:
            return ""
        return f"{speaker}{sep}{content}"

    @staticmethod
    def _extract_scene(item: Dict) -> str:
        config = DataProcessorService._get_config("scene")
        sep = config.get("separator", "；")

        content = item.get("content", {})
        parts = []

        # 核心剧情
        if content.get("narrative_action"):
            label = config.get("narrative_action", "剧情")
            parts.append(f"{label}{sep}{content['narrative_action']}")

        # 环境信息
        if content.get("location"):
            label = config.get("location", "地点")
            parts.append(f"{label}{sep}{content['location']}")

        # 氛围标签
        if content.get("visual_mood_tags"):
            tags = content["visual_mood_tags"]
            if isinstance(tags, list):
                label = config.get("visual_mood_tags", "氛围")
                parts.append(f"{label}{sep}{'、'.join(tags)}")

        return sep.join(parts)

    @staticmethod
    def _extract_slice(item: Dict) -> str:
        config = DataProcessorService._get_config("slice")
        sep = config.get("separator", "；")

        analysis = item.get("slice_analysis") or {}
        parts = []

        if analysis.get("visual_summary"):
            label = config.get("visual_summary", "画面")
            parts.append(f"{label}{sep}{analysis['visual_summary']}")

        if analysis.get("narrative_summary"):
            label = config.get("narrative_summary", "剧情")
            parts.append(f"{label}{sep}{analysis['narrative_summary']}")

        return sep.join(parts)

    @staticmethod
    def _extract_frame(item: Dict) -> str:
        config = DataProcessorService._get_config("frame")
        sep = config.get("separator", "；")

        va = item.get("visual_analysis") or {}
        parts = []

        if va.get("subject"):
            label = config.get("subject", "主体")
            parts.append(f"{label}{sep}{va['subject']}")

        if va.get("action"):
            label = config.get("action", "动作")
            parts.append(f"{label}{sep}{va['action']}")

        if va.get("environment"):
            label = config.get("environment", "环境")
            parts.append(f"{label}{sep}{va['environment']}")

        # 补充其他字段 (Shot, Lighting, Mood)
        shot_type = va.get("shot_type")
        if shot_type:
            label = config.get("shot_type", "景别")
            val = None
            if isinstance(shot_type, dict):
                val = shot_type.get("label") or shot_type.get("value")
            elif isinstance(shot_type, str):
                val = shot_type
            if val:
                parts.append(f"{label}{sep}{val}")

        if va.get("lighting_time"):
            label = config.get("lighting_time", "光影")
            parts.append(f"{label}{sep}{va['lighting_time']}")

        if va.get("visual_mood_tags"):
            tags = va["visual_mood_tags"]
            if isinstance(tags, list) and tags:
                label = config.get("visual_mood_tags", "氛围")
                parts.append(f"{label}{sep}{'、'.join(tags)}")

        return sep.join(parts)
