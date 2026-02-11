from typing import Any, Dict, Optional, Union

from pydantic import BaseModel

# 复用 Refinery 定义的领域模型，确保全链路数据结构一致
from apps.atomflow.refinery.schemas import KeyframeItem, Scene, Slice, SubtitleItem


class RetrievalResult(BaseModel):
    """
    检索结果容器。
    将业务领域对象 (Content) 与检索元数据 (Metadata) 结合。
    """

    # 检索元数据
    score: float
    source: str  # "vector", "structured"
    type: str  # "scene", "dialogue", "frame", "slice"

    # 核心领域对象 (直接嵌入，不扁平化)
    content: Union[Scene, SubtitleItem, KeyframeItem, Slice, Dict[str, Any]]

    # 媒体上下文 (Hydrated Context)
    media_id: str
    media_title: str
    video_url: str
    image_url: Optional[str] = None
