import uuid
from typing import List, Optional

from pydantic import BaseModel, Field

from .enums import Gender, PitchLevel, RoleType, SceneType, ShotType, SliceType, SpeedLevel, VolumeLevel

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
# ==============================================================================


class RoleTypeLabel(LabelValue):
    """[约束结构] 角色类型标签"""

    value: RoleType


class AudioAnalysis(BaseModel):
    """
    [音频特征] 对白声学分析结果。
    """

    gender: Gender = Field(default=Gender.UNKNOWN, description="推测性别")
    pitch_level: PitchLevel = Field(default=PitchLevel.MID, description="音高等级")
    speed_level: SpeedLevel = Field(default=SpeedLevel.NORMAL, description="语速等级")
    volume_level: VolumeLevel = Field(default=VolumeLevel.NORMAL, description="音量等级")

    avg_pitch_hz: float = Field(default=0.0, description="平均基频 (Hz)")
    chars_per_sec: float = Field(default=0.0, description="语速 (字/秒)")
    rms_energy: float = Field(default=0.0, description="能量均方根")


class IdentifiedCharacterItem(BaseModel):
    """
    [角色档案] 识别出的角色信息。
    """

    name: str = Field(..., description="标准角色名")
    aliases: List[str] = Field(default_factory=list, description="在本集中出现的别名/昵称")
    role_type: Optional[RoleTypeLabel] = Field(default=None, description="角色类型 (Value + Label)")
    description: Optional[str] = Field(None, description="基于本集剧情推断的角色描述")


class SubtitleItem(BaseModel):
    """
    Refinery 全链路标准台词单元。
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="唯一标识UUID")
    index: int = Field(..., description="全局递增序号")
    content: str = Field(..., description="对白文本内容")
    start_time: float = Field(..., description="起始秒数")
    end_time: float = Field(..., description="结束秒数")
    speaker: str = Field(default="Unknown", description="角色名")
    reasoning: Optional[str] = Field(default=None, description="AI推理依据/置信度说明")
    audio_analysis: Optional[AudioAnalysis] = Field(default=None, description="声学特征分析")
    voice_mood: Optional[str] = Field(default=None, description="AI推断的语气/情感标签 (配音参考)")
    original_indices: Optional[List[int]] = Field(default=None, description="合并前的原始索引列表")

    class Config:
        extra = "ignore"


# ==============================================================================
# 2. 视觉与关键帧域 (Visual & Keyframe Domain)
# ==============================================================================


class ShotTypeLabel(LabelValue):
    """[约束结构] 景别标签"""

    value: ShotType


class FrameBase(BaseModel):
    """
    [最小单元] 物理帧数据容器。
    """

    timestamp: float = Field(..., description="帧在视频中的时间戳（秒）")
    path: str = Field(..., description="相对路径")


class VisualAnalysis(BaseModel):
    """
    [Cloud API 响应] 视觉分析结果。
    """

    shot_type: Optional[ShotTypeLabel] = Field(None, description="Main shot size (Value + Label)")
    environment: Optional[str] = Field(None, description="Physical environment")
    subject: Optional[str] = None
    action: Optional[str] = None
    lighting_time: Optional[str] = Field(None, description="Time or lighting characteristics")
    visual_mood_tags: List[str] = Field(default_factory=list, description="视觉氛围标签")

    class Config:
        extra = "allow"


class KeyframeItem(FrameBase):
    """
    [核心数据结构] 关键帧完整元数据。
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="唯一标识UUID")
    slice_id: str = Field(..., description="所属切片的UUID")
    timestamp: float = Field(..., description="帧在视频中的时间戳（秒）")
    path: str = Field(..., description="相对路径 (本地或云端)")
    digest: Optional[str] = Field(default=None, description="文件内容摘要 (MD5/SHA256)")
    reason: Optional[str] = Field(default=None, description="抽帧原因")
    quality_score: Optional[float] = Field(default=None, description="帧质量分数")
    filter_reason: Optional[str] = Field(default=None, description="被过滤原因")
    visual_analysis: Optional[VisualAnalysis] = Field(default=None, description="云端 VLM 分析结果")


# ==============================================================================
# 3. 切片域 (Slice Domain)
# ==============================================================================


class SliceTypeLabel(LabelValue):
    """[约束结构] 切片类型标签"""

    value: SliceType


class AudioContent(BaseModel):
    """音频内容容器 (占位)"""

    pass


class SliceAnalysis(BaseModel):
    """
    [中间产物] 切片级语义分析结果。
    """

    narrative_summary: Optional[str] = Field(None, description="切片叙事摘要")
    visual_summary: Optional[str] = Field(None, description="切片视觉摘要")
    tags: List[str] = Field(default_factory=list, description="切片语义标签")


class Slice(BaseModel):
    """
    [核心容器] 多模态切片。
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="唯一标识UUID")
    index: int = Field(..., description="全局递增序号")
    start_time: float
    end_time: float
    type: SliceTypeLabel = Field(..., description="visual_segment | dialogue (Value + Label)")

    dialogue_ids: List[str] = Field(default_factory=list, description="关联对白UUID列表")
    frame_ids: List[str] = Field(default_factory=list, description="关联关键帧UUID列表")

    audio_contents: AudioContent = Field(default_factory=AudioContent)
    slice_analysis: Optional[SliceAnalysis] = Field(default=None, description="切片语义分析结果")


# ==============================================================================
# 4. 技术元数据 (Technical Metadata)
# ==============================================================================


class VideoMeta(BaseModel):
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class TechMeta(BaseModel):
    """对应 tech_meta"""

    container: Optional[str] = None
    size: int = 0
    video: VideoMeta = Field(default_factory=VideoMeta)


# ==============================================================================
# 5. 场景域 (Scene Domain)
# ==============================================================================


class SceneTypeLabel(LabelValue):
    """
    [约束结构] 场景类型标签。
    """

    value: SceneType


class SceneContent(BaseModel):
    """
    场景业务载体
    """

    narrative_action: str = Field(..., description="叙事动作/核心事件")
    location: Optional[str] = Field(None, description="主要地点")
    scene_type: Optional[SceneTypeLabel] = Field(None, description="功能类型 (Value + Label)")
    visual_mood_tags: List[str] = Field(default_factory=list, description="视觉氛围标签")
    camera_logic: Optional[str] = Field(None, description="运镜/剪辑逻辑")
    character_dynamics: Optional[str] = Field(None, description="角色张力/关系")
    reason: Optional[str] = Field(None, description="AI 分组/切分的理由")


class Scene(BaseModel):
    """
    [业务聚合结果] 场景单元。
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="唯一标识UUID")
    index: int = Field(..., description="全局递增序号")
    start_time: float = Field(..., description="场景的起始时间（秒）")
    end_time: float = Field(..., description="场景的结束时间（秒）")
    content: SceneContent = Field(..., description="场景的语义内容")
    slice_ids: List[str] = Field(..., description="构成此场景的原始 Slice UUID 列表")
