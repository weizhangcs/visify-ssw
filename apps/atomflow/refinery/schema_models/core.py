from typing import List, Optional

from pydantic import BaseModel, Field

from .audio import AudioContent
from .dialogue import SubtitleItem
from .visual import VisualContent


class MultimodalSlice(BaseModel):
    """
    [核心容器] 多模态切片。

    Material.slices 的元素结构。
    将时间轴上的一个片段聚合了视觉、听觉和文本信息。
    """

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
    """对应 tech_meta，存储 FFprobe 提取的技术元数据"""

    container: Optional[str] = None
    size: int = 0
    video: VideoStreamMeta = Field(default_factory=VideoStreamMeta)
