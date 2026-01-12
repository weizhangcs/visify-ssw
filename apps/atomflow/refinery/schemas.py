import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

# ==============================================================================
# 0. 基础原语 (Primitives & Shared)
# ==============================================================================


class LabelValue(BaseModel):
    """
    [通用结构] 标签项 (Value + Label)。
    用于存储枚举值的机器码和人类可读标签。
    """

    value: str
    label: str


# ==============================================================================
# 1. 对白与音频域 (Dialogue & Audio Domain)
# 对应 Material.dialogues / Material.identified_characters
# ==============================================================================

# --- Enums (枚举定义) ---


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


# --- Label Wrappers (标签封装) ---


class RoleTypeLabel(LabelValue):
    """[约束结构] 角色类型标签"""

    value: RoleType


# --- Models (数据模型) ---


class AudioAnalysis(BaseModel):
    """
    [音频特征] 对白声学分析结果。
    通常由音频分析模型产出，用于辅助情感判断或角色识别。
    """

    # [Optimization] 使用 Enum 替代魔法字符串，确保 Service 层产出符合契约
    gender: Gender = Field(default=Gender.UNKNOWN, description="推测性别")
    pitch_level: PitchLevel = Field(default=PitchLevel.MID, description="音高等级")
    speed_level: SpeedLevel = Field(default=SpeedLevel.NORMAL, description="语速等级")
    volume_level: VolumeLevel = Field(default=VolumeLevel.NORMAL, description="音量等级")

    # 原始数值 (用于调试或更精细的聚类)
    avg_pitch_hz: float = Field(default=0.0, description="平均基频 (Hz)")
    chars_per_sec: float = Field(default=0.0, description="语速 (字/秒)")
    rms_energy: float = Field(default=0.0, description="能量均方根")


class IdentifiedCharacterItem(BaseModel):
    """
    [角色档案] 识别出的角色信息。
    存储在 Material.identified_characters 列表中的单元。
    """

    name: str = Field(..., description="标准角色名")
    aliases: List[str] = Field(default_factory=list, description="在本集中出现的别名/昵称")
    role_type: Optional[RoleTypeLabel] = Field(default=None, description="角色类型 (Value + Label)")
    description: Optional[str] = Field(None, description="基于本集剧情推断的角色描述")


class SubtitleItem(BaseModel):
    """
    Refinery 全链路标准台词单元。

    1. 对齐 VSS Cloud 的 SubtitleInputItem。
    2. 作为 Material.dialogues 列表元素的存储标准。
    """

    index: int = Field(..., description="行号索引")
    content: str = Field(..., description="对白文本内容")
    start_time: float = Field(..., description="起始秒数")
    end_time: float = Field(..., description="结束秒数")
    speaker: str = Field(default="Unknown", description="角色名")
    reasoning: Optional[str] = Field(default=None, description="AI推理依据/置信度说明")
    audio_analysis: Optional[AudioAnalysis] = Field(default=None, description="声学特征分析")
    voice_mood: Optional[str] = Field(default=None, description="AI推断的语气/情感标签 (配音参考)")
    original_indices: Optional[List[int]] = Field(default=None, description="合并前的原始索引列表")

    class Config:
        extra = "ignore"  # 允许云端返回额外字段但不报错，保持向后兼容


# ==============================================================================
# 2. 视觉与关键帧域 (Visual & Keyframe Domain)
# 对应 Material.keyframe_map
# ==============================================================================

# --- Enums ---


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


# --- Label Wrappers ---


class ShotTypeLabel(LabelValue):
    """[约束结构] 景别标签"""

    value: ShotType


# --- Models ---


class FrameBase(BaseModel):
    """
    [最小单元] 物理帧数据容器。
    仅包含最基础的时间戳和路径信息。
    """

    timestamp: float = Field(..., description="帧在视频中的时间戳（秒）")
    path: str = Field(..., description="相对路径")


class VisualAnalysis(BaseModel):
    """
    [Cloud API 响应] 视觉分析结果。
    对应 VSS Cloud Visual Analyzer 的输出结构。
    """

    # [Optimization] 升级为强类型 Label
    shot_type: Optional[ShotTypeLabel] = Field(None, description="Main shot size (Value + Label)")
    environment: Optional[str] = Field(None, description="Physical environment (e.g., Indoor-Bedroom, Outdoor-Street)")
    subject: Optional[str] = None
    action: Optional[str] = None
    lighting_time: Optional[str] = Field(None, description="Time or lighting characteristics (e.g., Day, Night, Dusk)")
    visual_mood_tags: List[str] = Field(default_factory=list, description="视觉氛围标签")

    class Config:
        extra = "allow"


class KeyframeItem(FrameBase):
    """
    [核心数据结构] 关键帧完整元数据。

    作为 Material.keyframe_map 的 Value 结构。
    记录了帧的生命周期：从本地提取 -> 云端同步 -> 视觉分析。
    """

    frame_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="帧的唯一标识符")
    slice_id: int = Field(..., description="所属切片的ID")
    timestamp: float = Field(..., description="帧在视频中的时间戳（秒）")
    path: str = Field(..., description="相对路径 (本地或云端)")
    digest: Optional[str] = Field(default=None, description="文件内容摘要 (MD5/SHA256)")
    reason: Optional[str] = Field(
        default=None, description="抽帧原因：slice_boundary | internal_scene_change | fallback_mid"
    )
    quality_score: Optional[float] = Field(default=None, description="帧质量分数")
    filter_reason: Optional[str] = Field(default=None, description="被过滤原因：black_frame | white_frame | blurry_frame")
    visual_analysis: Optional[VisualAnalysis] = Field(default=None, description="云端 VLM 分析结果")


# ==============================================================================
# 3. 切片域 (Slice Domain)
# 对应 Material.slices
# ==============================================================================

# --- Enums ---


class SliceType(str, Enum):
    """
    切片类型枚举
    """

    VISUAL_SEGMENT = "visual_segment"
    DIALOGUE = "dialogue"


# --- Label Wrappers ---


class SliceTypeLabel(LabelValue):
    """[约束结构] 切片类型标签"""

    value: SliceType


# --- Models ---


class AudioContent(BaseModel):
    """音频内容容器 (占位)"""

    pass


class SliceAnalysis(BaseModel):
    """
    [中间产物] 切片级语义分析结果。
    由 SliceAnalyzer 产出，用于辅助 SliceRegrouper 进行聚类。
    """

    narrative_summary: Optional[str] = Field(None, description="切片叙事摘要")
    visual_summary: Optional[str] = Field(None, description="切片视觉摘要")
    tags: List[str] = Field(default_factory=list, description="切片语义标签")


class Slice(BaseModel):
    """
    [核心容器] 多模态切片。

    Material.slices 的元素结构。
    将时间轴上的一个片段聚合了视觉、听觉和文本信息。
    """

    slice_id: int
    start_time: float
    end_time: float
    type: SliceTypeLabel = Field(..., description="visual_segment | dialogue (Value + Label)")
    text_contents: List[SubtitleItem] = Field(default_factory=list, description="无损对白数据")
    visual_contents: List[KeyframeItem] = Field(default_factory=list, description="无损视觉分析数据")
    audio_contents: AudioContent = Field(default_factory=AudioContent)
    slice_analysis: Optional[SliceAnalysis] = Field(default=None, description="切片语义分析结果")


# ==============================================================================
# 4. 技术元数据 (Technical Metadata)
# 对应 Material.tech_meta
# ==============================================================================


class VideoMeta(BaseModel):
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class TechMeta(BaseModel):
    """对应 tech_meta，存储 FFprobe 提取的技术元数据"""

    container: Optional[str] = None
    size: int = 0
    video: VideoMeta = Field(default_factory=VideoMeta)


# ==============================================================================
# 5. 场景域 (Scene Domain)
# 对应 Material.scenes
# ==============================================================================

# --- Enums ---


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


# --- Label Wrappers ---


class SceneTypeLabel(LabelValue):
    """
    [约束结构] 场景类型标签。
    强制 value 必须是 SceneType 枚举值。
    """

    value: SceneType


# --- Models ---


class SceneContent(BaseModel):
    """
    场景业务载体
    """

    narrative_action: str = Field(..., description="叙事动作/核心事件")
    location: Optional[str] = Field(None, description="主要地点")
    scene_type: Optional[SceneTypeLabel] = Field(None, description="功能类型 (Value + Label)")
    visual_mood_tags: List[str] = Field(default_factory=list, description="视觉氛围标签")
    camera_logic: Optional[str] = Field(None, description="运镜/剪辑逻辑 (e.g., Static, Fast cuts)")
    character_dynamics: Optional[str] = Field(None, description="角色张力/关系")
    reason: Optional[str] = Field(None, description="AI 分组/切分的理由")


class Scene(BaseModel):
    """
    [业务聚合结果] 场景单元。
    由 SliceRegrouper 算子生成，是 Refinery 流程的最终产出之一。
    """

    scene_id: int = Field(..., description="场景的顺序 ID")
    start_time: float = Field(..., description="场景的起始时间（秒）")
    end_time: float = Field(..., description="场景的结束时间（秒）")
    content: SceneContent = Field(..., description="场景的语义内容")
    slice_ids: List[int] = Field(..., description="构成此场景的原始 MultimodalSlice ID 列表")
