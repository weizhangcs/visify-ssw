from enum import Enum

# [修正] 这是一个 Django Model Enum，在 Pydantic 中我们使用 str, Enum


class ShotType(str, Enum):
    EXTREME_CLOSE_UP = "extreme_close_up"
    CLOSE_UP = "close_up"
    MEDIUM_CLOSE_UP = "medium_close_up"
    MEDIUM_SHOT = "medium_shot"
    MEDIUM_LONG_SHOT = "medium_long_shot"
    LONG_SHOT = "long_shot"
    EXTREME_LONG_SHOT = "extreme_long_shot"
    ESTABLISHING_SHOT = "establishing_shot"
    OTHER = "other"

    @classmethod
    def get_label(cls, value: str, lang: str = "en") -> str:
        return SHOT_TYPE_LABELS.get(value, {}).get(lang, value)


SHOT_TYPE_LABELS = {
    "extreme_close_up": {"zh": "大特写", "en": "Extreme Close Up"},
    "close_up": {"zh": "特写", "en": "Close Up"},
    "medium_close_up": {"zh": "近景", "en": "Medium Close Up"},
    "medium_shot": {"zh": "中景", "en": "Medium Shot"},
    "medium_long_shot": {"zh": "中远景", "en": "Medium Long Shot"},
    "long_shot": {"zh": "远景", "en": "Long Shot"},
    "extreme_long_shot": {"zh": "大远景", "en": "Extreme Long Shot"},
    "establishing_shot": {"zh": "建立镜头", "en": "Establishing Shot"},
    "other": {"zh": "其他", "en": "Other"},
}


class SceneType(str, Enum):
    """
    场景类型
    严格对齐 Cloud 端 ScenePreAnnotator 的 Enum 定义
    """

    DIALOGUE = "dialogue"
    ACTION = "action"
    MONTAGE = "montage"
    ESTABLISHING = "establishing"
    EMOTIONAL = "emotional"
    UNKNOWN = "unknown"
