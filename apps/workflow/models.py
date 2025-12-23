# /apps/workflow/models.py

# --- 从新的 transcoding 子包导入 ---
from .annotation.jobs import AnnotationJob

# --- 从 annotation 子包导入 ---
from .annotation.projects import AnnotationProject

# --- 从 character_annotation 子包导入 ---
from .character_annotation.models import CharacterAnnotationJob, CharacterAnnotationProject
from .creative.jobs import CreativeJob
from .creative.models import CreativeProject

# --- 从新的 delivery 子包导入 ---
from .delivery.jobs import DeliveryJob

# --- 从 inference 子包导入 ---
from .inference.projects import InferenceProject
from .scene_annotation.models import SceneAnnotationJob, SceneAnnotationProject
from .transcoding.jobs import TranscodingJob
from .transcoding.projects import TranscodingProject

__all__ = [
    "AnnotationJob",
    "AnnotationProject",
    "CreativeJob",
    "CreativeProject",
    "DeliveryJob",
    "InferenceProject",
    "TranscodingJob",
    "TranscodingProject",
    "CharacterAnnotationProject",
    "CharacterAnnotationJob",
    "SceneAnnotationJob",
    "SceneAnnotationProject",
]
