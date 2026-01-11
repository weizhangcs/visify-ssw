from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ==============================================================================
# 1. 输入侧 Schemas (MultimodalSlice)
# ==============================================================================


class AudioAnalysis(BaseModel):
    gender: str = Field(default="Unknown")
    model_config = ConfigDict(extra="ignore")


class SubtitleItem(BaseModel):
    index: int
    content: str
    start_time: float
    end_time: float
    speaker: str = "Unknown"
    audio_analysis: Optional[AudioAnalysis] = None
    model_config = ConfigDict(extra="ignore")


class VisualAnalysisData(BaseModel):
    # 兼容上游 Visual Analyzer 的输出 (可能是 LabelItem 字典，也可能是旧的字符串)
    shot_type: Optional[Any] = None
    environment: Optional[str] = None
    subject: Optional[str] = None
    action: Optional[str] = None
    visual_mood_tags: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")


class FrameDataInput(BaseModel):
    frame_id: str
    timestamp: float
    path: str
    digest: Optional[str] = None
    visual_analysis: Optional[VisualAnalysisData] = None
    model_config = ConfigDict(extra="ignore")


class MultimodalSlice(BaseModel):
    """
    [核心容器] 多模态切片。
    """

    slice_id: int
    start_time: float
    end_time: float
    type: str
    text_contents: List[SubtitleItem] = Field(default_factory=list)
    visual_contents: List[FrameDataInput] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")


# ==============================================================================
# 2. 任务 Payload
# ==============================================================================


class SliceRegrouperServiceParams(BaseModel):
    """Technical parameters for DEBUG mode"""

    model: Optional[str] = Field(None, description="LLM model name")
    max_slices_per_batch: Optional[int] = Field(None, description="Slices per batch")
    temperature: Optional[float] = Field(None, description="Temperature for LLM")
    max_retries: Optional[int] = Field(None, description="Max retries")


class SliceRegrouperPayload(BaseModel):
    """
    [Execution Schema] REFINERY_SLICE_REGROUPER 任务载荷
    """

    lang: str = Field("zh", description="Language code")
    mode: Literal["PROD", "DEBUG"] = Field("PROD", description="Operation mode")

    # Data Source
    slices_file_path: Optional[str] = Field(None, description="Path to the rich slices JSON file (Production)")
    slices: Optional[List[MultimodalSlice]] = Field(None, description="Direct list of slices (Debug)")

    # Debug Params
    service_params: Optional[SliceRegrouperServiceParams] = Field(default_factory=SliceRegrouperServiceParams)

    @model_validator(mode="after")
    def check_data_source(self):
        if not self.slices and not self.slices_file_path:
            raise ValueError("Either 'slices' or 'slices_file_path' must be provided.")

        if self.mode == "PROD":
            sp = self.service_params
            if sp and (sp.model or sp.max_slices_per_batch or sp.temperature or sp.max_retries):
                raise ValueError("In PROD mode, technical parameters are not allowed in payload.")
        return self
