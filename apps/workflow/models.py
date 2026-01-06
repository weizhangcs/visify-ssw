# /apps/workflow/models.py

# --- 从新的 transcoding 子包导入 ---
from .annotation.jobs import AnnotationJob

# --- 从 annotation 子包导入 ---
from .annotation.projects import AnnotationProject
from .creative.jobs import CreativeJob
from .creative.models import CreativeProject

# --- 从新的 delivery 子包导入 ---
from .delivery.jobs import DeliveryJob

# --- 从 inference 子包导入 ---
from .inference.projects import InferenceProject

__all__ = [
    "AnnotationJob",
    "AnnotationProject",
    "CreativeJob",
    "CreativeProject",
    "DeliveryJob",
    "InferenceProject",
]
