from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class VisualFrameInput(BaseModel):
    """
    [Execution Schema] 用于视觉分析的帧输入
    """

    frame_id: str = Field(..., description="Unique identifier for the frame")
    path: str = Field(..., description="GCS URI (gs://) or local path to the image")
    digest: Optional[str] = Field(None, description="Optional file digest")


class VisualAnalyzerServiceParams(BaseModel):
    """Technical parameters for DEBUG mode"""

    model: Optional[str] = Field(None, description="Gemini model name")
    batch_size: Optional[int] = Field(None, description="Batch size for processing")
    max_workers: Optional[int] = Field(None, description="Max concurrent workers")
    temperature: Optional[float] = Field(None, description="Temperature for LLM")
    max_retries: Optional[int] = Field(None, description="Max retries for LLM calls")


class VisualAnalyzerPayload(BaseModel):
    """
    [Execution Schema] REFINERY_VISUAL_ANALYZER 任务载荷
    """

    lang: str = Field("en", description="Language code for prompt and response")
    mode: Literal["PROD", "DEBUG"] = Field("PROD", description="Operation mode")

    # Data Source
    frames_file_path: Optional[str] = Field(
        None, description="Path to external JSON file containing frames list (Production)"
    )
    frames: Optional[List[VisualFrameInput]] = Field(None, description="Direct list of frames (Debug/Small Batch)")

    # Debug Params
    service_params: Optional[VisualAnalyzerServiceParams] = Field(default_factory=VisualAnalyzerServiceParams)

    @model_validator(mode="after")
    def check_data_source(self):
        if not self.frames and not self.frames_file_path:
            raise ValueError("Either 'frames' or 'frames_file_path' must be provided.")

        if self.mode == "PROD":
            sp = self.service_params
            if sp and (sp.model or sp.batch_size or sp.max_workers or sp.temperature or sp.max_retries):
                raise ValueError("In PROD mode, technical parameters are not allowed in payload.")
        return self
