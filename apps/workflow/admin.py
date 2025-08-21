# 文件路径: apps/configuration/admin.py

from django.contrib import admin
from unfold.admin import ModelAdmin
from .jobs.transcodingJob import TranscodingJob

@admin.register(TranscodingJob)

class JobsAdmin(ModelAdmin): # <-- 核心修正：多重继承
    fieldsets = (
        ("工作流任务管理 (Workflow)", {
            'fields': ('id',)
        }),
    )