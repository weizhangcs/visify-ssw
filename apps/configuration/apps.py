# 文件路径: apps/configuration/apps.py

from django.apps import AppConfig


class ConfigurationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.configuration'
    verbose_name = '系统集成设置'