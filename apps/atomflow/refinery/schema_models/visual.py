import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class VisualAnalysisData(BaseModel):
    """
    [Cloud API 响应] 视觉分析结果。
    对应 VSS Cloud Visual Analyzer 的输出结构。
    """

    shot_type: Optional[str] = Field(None, description="Main shot size (Label or Enum Key)")
    environment: Optional[str] = Field(None, description="Physical environment (e.g., Indoor-Bedroom, Outdoor-Street)")
    subject: Optional[str] = None
    action: Optional[str] = None
    lighting_time: Optional[str] = Field(None, description="Time or lighting characteristics (e.g., Day, Night, Dusk)")
    visual_mood_tags: List[str] = Field(default_factory=list, description="视觉氛围标签")

    class Config:
        extra = "allow"


class FrameData(BaseModel):
    """
    [最小单元] 物理帧数据容器。
    仅包含最基础的时间戳和路径信息。
    """

    timestamp: float = Field(..., description="帧在视频中的时间戳（秒）")
    path: str = Field(..., description="相对路径")


class FrameDataInput(FrameData):
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
    visual_analysis: Optional[VisualAnalysisData] = Field(default=None, description="云端 VLM 分析结果")


class FrameDataOutput(BaseModel):
    """
    [结果数据] 帧数据输出容器 (VLM 识别结果)。
    通常用于向前端展示或作为下游任务的输入。
    """

    timestamp: float = Field(..., description="帧在视频中的时间戳（秒）")
    path: str = Field(..., description="云端路径")  # 最终的云端路径
    # VLM 识别结果
    shot_type: Optional[str] = Field(default=None, description="The camera shot size.")
    subject: Optional[str] = Field(default=None, description="Main subject (Person/Object). Keep brief.")
    action: Optional[str] = Field(default=None, description="Physical action occurring. Keep brief.")
    visual_mood_tags: List[str] = Field(
        default_factory=list, description="A list of 1-3 keywords describing the lighting and atmosphere."
    )


class VisualContent(BaseModel):
    """
    视觉内容容器。
    聚合了切片级别的视觉分析结果。
    """

    # 最终聚合的视觉分析结果
    frames_analysis: List[FrameDataOutput] = Field(default_factory=list, description="经过 VLM 识别后的关键帧语义结果")
    # 切片级别的视觉摘要 (如果 Cloud VLM 提供)
    slice_summary: Optional[str] = Field(default=None, description="切片视觉内容总结")


class VisualFrameInput(BaseModel):
    frame_id: str = Field(..., description="Unique identifier for the frame to map results back")
    path: str = Field(..., description="GCS URI or local path to the image")
    digest: Optional[str] = Field(None, description="Optional file digest for validation")


class VisualAnalyzerPayload(BaseModel):
    lang: str = Field("en", description="Language code for prompt and response")
    visual_model: str = Field(..., description="Gemini model name")
    frames: List[VisualFrameInput]


class FrameAnalysisResult(BaseModel):
    frame_id: str
    visual_analysis: VisualAnalysisData


class BatchVisualOutput(BaseModel):
    annotated_frames: List[FrameAnalysisResult]
    stats: Optional[Dict] = None
    usage_report: Optional[Dict] = None
