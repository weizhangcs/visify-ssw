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
    """单帧画面的数据容器"""

    position: str = Field(..., description="mid | start | end")
    path: str = Field(..., description="相对路径")


class VisualContent(BaseModel):
    """视觉内容容器"""

    frames: List[FrameData] = Field(default_factory=list, description="该切片下的关键帧")
    # keyframe_map: Dict = Field(default_factory=dict, description="本地视觉分析结果")
    # visual_analysis: Dict = Field(default_factory=dict, description="云端VLM分析结果")


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
