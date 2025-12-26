# 文件路径: apps/refinery/apps.py

from django.apps import AppConfig


class RefineryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.refinery"
    verbose_name = "生产数据精炼"
