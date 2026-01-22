from enum import Enum


class Gender(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    UNKNOWN = "Unknown"


class PitchLevel(str, Enum):
    HIGH = "High"
    MID = "Mid"
    LOW = "Low"


class SpeedLevel(str, Enum):
    FAST = "Fast"
    NORMAL = "Normal"
    SLOW = "Slow"


class VolumeLevel(str, Enum):
    LOUD = "Loud"
    NORMAL = "Normal"
    QUIET = "Quiet"


class RoleType(str, Enum):
    """
    角色类型枚举
    """

    MAIN = "main"
    SUPPORTING = "supporting"
    GUEST = "guest"
    UNKNOWN = "unknown"


class ShotType(str, Enum):
    """景别枚举 (基于 VSS Cloud 定义)"""

    ECU = "extreme_close_up"
    CU = "close_up"
    MCU = "medium_close_up"
    MS = "medium_shot"
    MLS = "medium_long_shot"
    LS = "long_shot"
    ELS = "extreme_long_shot"
    EST = "establishing_shot"
    UNKNOWN = "unknown"
    OTHER = "other"


class SliceType(str, Enum):
    """
    切片类型枚举
    """

    VISUAL_SEGMENT = "visual_segment"
    DIALOGUE = "dialogue"


class SceneType(str, Enum):
    """
    场景类型
    """

    DIALOGUE = "dialogue"
    ACTION = "action"
    MONTAGE = "montage"
    ESTABLISHING = "establishing"
    EMOTIONAL = "emotional"
    UNKNOWN = "unknown"


class HighlightType(str, Enum):
    """高光类型枚举"""

    ACTION = "Action"
    EMOTIONAL = "Emotional"
    DIALOGUE = "Dialogue"
    SUSPENSE = "Suspense"
    INFORMATION = "Information"
    HUMOR = "Humor"
    OTHER = "Other"


class HighlightMood(str, Enum):
    """高光情绪枚举"""

    EXCITING = "Exciting"
    SATISFYING = "Satisfying"
    HEART_WRENCHING = "Heart-wrenching"
    SWEET = "Sweet"
    HILARIOUS = "Hilarious"
    TERRIFYING = "Terrifying"
    HEALING = "Healing"
    TOUCHING = "Touching"
    TENSE = "Tense"


class DataOrigin(str, Enum):
    """数据来源枚举"""

    HUMAN = "human"
    AI_ASR = "ai_asr"
    AI_LLM = "ai_llm"
    AI_CV = "ai_cv"
    AI_OCR = "ai_ocr"


# 官方翻译映射表 (Moved from DTOs to Shared Kernel)
SHOT_TYPE_LABELS = {
    "zh": {
        ShotType.ECU: "大特写",
        ShotType.CU: "特写",
        ShotType.MCU: "近景",
        ShotType.MS: "中景",
        ShotType.MLS: "中远景",
        ShotType.LS: "远景",
        ShotType.ELS: "大远景",
        ShotType.EST: "建立镜头",
        ShotType.UNKNOWN: "未知",
        ShotType.OTHER: "其他",
    },
    "en": {
        ShotType.ECU: "Extreme Close Up",
        ShotType.CU: "Close Up",
        ShotType.MCU: "Medium Close Up",
        ShotType.MS: "Medium Shot",
        ShotType.MLS: "Medium Long Shot",
        ShotType.LS: "Long Shot",
        ShotType.ELS: "Extreme Long Shot",
        ShotType.EST: "Establishing Shot",
        ShotType.UNKNOWN: "Unknown",
        ShotType.OTHER: "Other",
    },
}

# SceneType Labels usually handled by Django TextChoices in Workbench,
# but kept here for pure python usage if needed.
