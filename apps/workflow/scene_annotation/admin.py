# apps/workflow/scene_annotation/admin.py

from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from .models import SceneAnnotationJob, SceneAnnotationProject
from .views import trigger_scene_annotation_view


@admin.register(SceneAnnotationProject)
class SceneAnnotationProjectAdmin(ModelAdmin):
    # 对齐 TranscodingProjectAdmin 布局
    list_display = ("name", "asset", "status", "project_actions")
    list_display_links = ("name",)
    list_per_page = 20

    fields = ("name", "asset", "description", "status")
    readonly_fields = ("status",)

    @admin.display(description=_("操作"))
    def project_actions(self, obj):
        # 仅在 PENDING 状态显示启动按钮，对齐转码模块逻辑
        if obj.status == "PENDING":
            info = self.model._meta.app_label, self.model._meta.model_name
            trigger_url = reverse("admin:%s_%s_trigger" % info, args=[obj.pk])
            return format_html(
                '<a href="{}" class="button variant-primary" style="padding: 4px 10px;">▶️ 启动切片</a>', trigger_url
            )
        return format_html('<span class="badge">{}</span>', obj.get_status_display())

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            path(
                "<path:project_id>/trigger/",
                self.admin_site.admin_view(trigger_scene_annotation_view),
                name="%s_%s_trigger" % info,
            ),
        ]
        return custom_urls + urls


@admin.register(SceneAnnotationJob)
class SceneAnnotationJobAdmin(ModelAdmin):
    # 对齐 TranscodingJobAdmin 布局
    list_display = ("media", "project", "status", "cloud_task_id", "modified")
    list_filter = ("status", "project")
    readonly_fields = ("project", "media", "cloud_task_id", "result")
    list_per_page = 20
