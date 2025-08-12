# 文件路径: apps/configuration/admin.py

from django.contrib import admin
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin # <-- 核心修正：导入 Unfold 的 ModelAdmin
from .models import IntegrationSettings

@admin.register(IntegrationSettings)
class IntegrationSettingsAdmin(ModelAdmin, SingletonModelAdmin): # <-- 核心修正：多重继承
    fieldsets = (
        ("权限管理 (Authorization)", {
            'fields': ('superuser_emails',)
        }),
    )