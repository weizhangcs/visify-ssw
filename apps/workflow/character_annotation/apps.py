# 文件路径: apps/workflow/character_annotation/apps.py

from django.apps import AppConfig


class CharacterAnnotationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workflow.character_annotation"
    label = "character_annotation"  # 显式声明 label，确保 apps.get_model 能找到
