# 文件路径: apps/configuration/admin.py

from django.contrib import admin
from solo.admin import SingletonModelAdmin
from .models import IntegrationSettings

@admin.register(IntegrationSettings)
class IntegrationSettingsAdmin(SingletonModelAdmin):
    fieldsets = (
        ("Authentik OIDC (for Django)", {
            'fields': ('oidc_rp_client_id', 'oidc_rp_client_secret')
        }),
        ("权限管理 (Authorization)", {
            'fields': ('superuser_emails',)
        }),
    )