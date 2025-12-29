# 文件路径: apps/refinery/admin.py

from django.contrib import admin
from django.template.loader import render_to_string
from django.urls import path
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .models import Material
from .views import manual_retry_step_view, material_pipeline_state_api


@admin.register(Material)
class MaterialAdmin(ModelAdmin):
    list_display = ("media_title", "status_badge", "duration_display", "modified")
    readonly_fields = ("id", "status", "pipeline_monitor_ui", "error_log", "pipeline_metrics", "duration", "tech_meta")

    # 详情页字段排版
    fieldsets = (
        ("关联信息", {"fields": ("media", "id")}),
        ("生产管线监视器 (白盒)", {"fields": ("pipeline_monitor_ui",)}),
        ("状态与日志", {"fields": ("status", "error_log", "pipeline_metrics")}),
        ("技术指标", {"fields": ("duration", "tech_meta")}),
    )

    # --- 自定义展示列 ---

    @admin.display(description="关联媒体")
    def media_title(self, obj):
        return obj.media.title

    @admin.display(description="状态")
    def status_badge(self, obj):
        colors = {
            "READY": "bg-green-100 text-green-800",
            "FAILED": "bg-red-100 text-red-800",
            "PENDING": "bg-gray-100 text-gray-800",
        }
        color = colors.get(obj.status, "bg-blue-100 text-blue-800")
        return format_html(
            '<span class="px-2 py-1 rounded text-xs font-bold {}">{}</span>', color, obj.get_status_display()
        )

    @admin.display(description="视频时长")
    def duration_display(self, obj):
        return f"{obj.duration:.2f}s" if obj.duration else "-"  # noqa: E231

    # --- 核心：白盒管线监视器渲染 ---

    @admin.display(description="管线执行状态 (White-box)")
    def pipeline_monitor_ui(self, obj):
        """渲染自定义监控模板"""
        # 我们将所有的渲染逻辑交给 template 处理，保持 admin 干净
        return render_to_string(
            "admin/refinery/material/pipeline_monitor.html",
            {
                "material": obj,
                "retry_url": f"/admin/refinery/material/{obj.id}/retry-step/",
                "state_url": f"/admin/refinery/material/{obj.id}/pipeline-state/",
            },
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path("<uuid:material_id>/pipeline-state/", self.admin_site.admin_view(material_pipeline_state_api)),
            path("<uuid:material_id>/retry-step/", self.admin_site.admin_view(manual_retry_step_view)),
        ]
        return custom_urls + urls
