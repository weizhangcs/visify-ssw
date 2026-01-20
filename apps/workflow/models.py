# /apps/workflow/models.py

# --- 从 annotation 子包导入 ---
from .annotation.jobs import AnnotationJob
from .annotation.projects import AnnotationProject

# --- 从 creative 子包导入 ---
from .creative.jobs import CreativeJob
from .creative.models import CreativeProject

__all__ = [
    "AnnotationJob",
    "AnnotationProject",
    "CreativeJob",
    "CreativeProject",
]
