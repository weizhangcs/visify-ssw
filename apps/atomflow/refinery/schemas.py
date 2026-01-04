import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class SubtitleItem(BaseModel):
    """
    Refinery 全链路标准台词单元。
    1. 对齐 VSS Cloud 的 SubtitleInputItem。
    2. 作为 Material.dialogue_track 列表元素的存储标准。
    """

    index: int = Field(..., description="行号索引")
    content: str = Field(..., description="对白文本内容")
    start_time: float = Field(..., description="起始秒数")
    end_time: float = Field(..., description="结束秒数")
    speaker: str = Field(default="Unknown", description="角色名")
    reasoning: Optional[str] = Field(default=None, description="AI推理依据/置信度说明")

    class Config:
        extra = "ignore"  # 允许云端返回额外字段但不报错，保持向后兼容


class FrameData(BaseModel):
    """[最小单元] 物理帧数据容器"""

    timestamp: float = Field(..., description="帧在视频中的时间戳（秒）")
    path: str = Field(..., description="相对路径")


class VisualAnalysisData(BaseModel):
    """[Cloud API 响应] 视觉分析结果"""

    shot_type: Optional[str] = Field(None, description="Main shot size (Label or Enum Key)")
    environment: Optional[str] = Field(None, description="Physical environment (e.g., Indoor-Bedroom, Outdoor-Street)")
    subject: Optional[str] = None
    action: Optional[str] = None
    lighting_time: Optional[str] = Field(None, description="Time or lighting characteristics (e.g., Day, Night, Dusk)")
    visual_mood_tags: List[str] = Field(default_factory=list, description="视觉氛围标签")

    class Config:
        extra = "allow"


class FrameDataInput(FrameData):
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
    visual_analysis: Optional[VisualAnalysisData] = Field(default=None, description="云端 VLM 分析结果")


class FrameDataOutput(BaseModel):
    """[结果数据] 帧数据输出容器 (VLM 识别结果)"""

    timestamp: float = Field(..., description="帧在视频中的时间戳（秒）")
    path: str = Field(..., description="云端路径")  # 最终的云端路径
    # VLM 识别结果
    shot_type: Optional[str] = Field(default=None, description="The camera shot size.")
    subject: Optional[str] = Field(default=None, description="Main subject (Person/Object). Keep brief.")
    action: Optional[str] = Field(default=None, description="Physical action occurring. Keep brief.")
    visual_mood_tags: List[str] = Field(
        default_factory=list, description="A list of 1-3 keywords describing the lighting and atmosphere."
    )
    # 原始的 L0/L1 数据也可以选择性保留
    # probe_data: Dict = Field(default_factory=dict, description="本地帧探测结果")


class VisualContent(BaseModel):
    """视觉内容容器"""

    # frames: List[FrameData] = Field(default_factory=list, description="该切片下的关键帧") # 移除，帧数据在 keyframe_map
    # probe_data: Dict = Field(default_factory=dict, description="本地帧探测结果（如亮度、模糊度）") # 移除，在 keyframe_map

    # 最终聚合的视觉分析结果
    frames_analysis: List[FrameDataOutput] = Field(default_factory=list, description="经过 VLM 识别后的关键帧语义结果")
    # 切片级别的视觉摘要 (如果 Cloud VLM 提供)
    slice_summary: Optional[str] = Field(default=None, description="切片视觉内容总结")


class AudioContent(BaseModel):
    """音频内容容器 (占位)"""

    pass


class MultimodalSlice(BaseModel):
    """[核心容器] 多模态切片"""

    slice_id: int
    start_time: float
    end_time: float
    type: str = Field(..., description="visual_segment | dialogue")
    text_contents: List[SubtitleItem] = Field(default_factory=list, description="无损对白数据")
    visual_contents: VisualContent = Field(default_factory=VisualContent)
    audio_contents: AudioContent = Field(default_factory=AudioContent)


class VideoStreamMeta(BaseModel):
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class TechMeta(BaseModel):
    """对应 tech_meta"""

    container: Optional[str] = None
    size: int = 0
    video: VideoStreamMeta = Field(default_factory=VideoStreamMeta)
