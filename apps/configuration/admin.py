# 文件路径: apps/configuration/admin.py

from django.contrib import admin
from solo.admin import SingletonModelAdmin
from unfold.admin import ModelAdmin

from .models import EncodingProfile, IntegrationSettings


@admin.register(IntegrationSettings)
class IntegrationSettingsAdmin(ModelAdmin, SingletonModelAdmin):  # <-- 核心修正：多重继承
    fieldsets = (
        ("权限管理 (Authorization)", {"fields": ("superuser_emails",)}),
        # [新增 Fieldset] 外部服务认证 Token
        ("云端服务配置 (Cloud Services)", {"fields": ("cloud_api_base_url", "cloud_instance_id", "cloud_api_key")}),
    )


@admin.register(EncodingProfile)
class EncodingProfileAdmin(ModelAdmin):
    list_display = ("name", "is_default", "container", "modified")
    list_filter = ("is_default",)  # 顺便也加一个过滤器
    search_fields = ("name", "description")
