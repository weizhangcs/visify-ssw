from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class SubtitleItem(BaseModel):
    """
    [Execution Schema] 用于云端推理的字幕项定义
    """

    index: int = Field(..., description="Original subtitle index")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    content: str = Field(..., description="Subtitle text content")


class SubtitleMergerServiceParams(BaseModel):
    """技术参数封装 (仅 DEBUG 模式使用)"""

    model: Optional[str] = Field(None, description="LLM model name")
    batch_size: Optional[int] = Field(None, description="Batch size for processing")
    temperature: Optional[float] = Field(None, description="Temperature for LLM")
    max_retries: Optional[int] = Field(None, description="Max retries for LLM calls")


class SubtitleMergerPayload(BaseModel):
    """
    [Execution Schema] REFINERY_SUBTITLE_MERGER 任务载荷
    """

    lang: str = Field("zh", description="Language code (zh, en)")
    mode: Literal["PROD", "DEBUG"] = Field("PROD", description="运行模式")
    service_params: Optional[SubtitleMergerServiceParams] = Field(
        default_factory=SubtitleMergerServiceParams, description="Technical parameters"
    )
    subtitles: Optional[List[SubtitleItem]] = Field(None, description="List of subtitles (Debug)")
    subtitle_file_path: Optional[str] = Field(None, description="Path to external JSON file (Production)")

    @model_validator(mode="after")
    def check_data_source(self):
        if not self.subtitles and not self.subtitle_file_path:
            raise ValueError("Either 'subtitles' or 'subtitle_file_path' must be provided.")
        if self.mode == "PROD":
            sp = self.service_params
            if sp and (sp.model or sp.batch_size or sp.temperature or sp.max_retries):
                raise ValueError(
                    "In PROD mode, technical parameters (service_params) are not allowed. They are sourced from config."
                )
        return self
