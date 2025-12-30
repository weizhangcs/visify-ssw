from typing import Optional

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
