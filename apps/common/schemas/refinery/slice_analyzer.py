from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 复用 SliceRegrouper 中定义的 MultimodalSlice 结构作为输入
# ==============================================================================
# 1. 输入侧 Schemas (MultimodalSlice - Local Copy for Isolation)
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
    [Input] 多模态切片输入。
    """

    slice_id: int
    start_time: float
    end_time: float
    type: str
    text_contents: List[SubtitleItem] = Field(default_factory=list)
    visual_contents: List[FrameDataInput] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")


class SliceAnalysis(BaseModel):
    """
    [Execution Schema] 切片分析结果
    """

    narrative_summary: Optional[str] = None
    visual_summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")


class AnalyzedSlice(BaseModel):
    """
    [Execution Schema] 包含分析结果的切片
    """

    slice_id: int
    slice_analysis: SliceAnalysis


class SliceAnalyzerServiceParams(BaseModel):
    """Technical parameters for DEBUG mode"""

    model: Optional[str] = Field(None, description="LLM model name")
    batch_size: Optional[int] = Field(None, description="Batch size")
    temperature: Optional[float] = Field(None, description="Temperature")
    max_retries: Optional[int] = Field(None, description="Max retries")


class SliceAnalyzerPayload(BaseModel):
    """
    [Execution Schema] REFINERY_SLICE_ANALYZER 任务载荷
    """

    lang: str = Field("zh", description="Language code")
    mode: Literal["PROD", "DEBUG"] = Field("PROD", description="Operation mode")

    # Data Source
    slices_file_path: Optional[str] = Field(None, description="Path to rich slices JSON (Production)")
    slices: Optional[List[MultimodalSlice]] = Field(None, description="Direct list (Debug)")

    # Debug Params
    service_params: Optional[SliceAnalyzerServiceParams] = Field(default_factory=SliceAnalyzerServiceParams)

    @model_validator(mode="after")
    def check_data_source(self):
        if not self.slices and not self.slices_file_path:
            raise ValueError("Either 'slices' or 'slices_file_path' must be provided.")

        if self.mode == "PROD":
            sp = self.service_params
            if sp and (sp.model or sp.batch_size or sp.temperature or sp.max_retries):
                raise ValueError("In PROD mode, technical parameters are not allowed in payload.")
        return self
