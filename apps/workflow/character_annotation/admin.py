# 文件路径: apps/workflow/character_annotation/admin.py

import logging

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext  # [修改] 直接导入 gettext
from unfold.admin import ModelAdmin, TabularInline

from .models import CharacterAnnotationJob, CharacterAnnotationProject
from .tasks import start_character_annotation_task

logger = logging.getLogger(__name__)


class CharacterAnnotationJobInline(TabularInline):
    model = CharacterAnnotationJob
    extra = 0
    can_delete = False
    fields = ("media", "status", "cloud_task_id", "output_ass_file", "modified")
    readonly_fields = ("media", "status", "cloud_task_id", "output_ass_file", "modified")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CharacterAnnotationProject)
class CharacterAnnotationProjectAdmin(ModelAdmin):
    list_display = ("name", "asset", "status", "created", "project_actions")
    list_filter = ("status", "asset")
    search_fields = ("name", "asset__title")
    readonly_fields = ("status",)

    inlines = [CharacterAnnotationJobInline]

    @admin.display(description=gettext("操作"))  # [修改] 使用 gettext
    def project_actions(self, obj):
        if obj.status in ["PENDING", "FAILED"]:
            url = reverse("admin:character_annotation_trigger", args=[obj.pk])
            return format_html('<a href="{}" class="button variant-primary">🚀 启动云端识别</a>', url)
        return format_html('<span class="text-gray-400">{}</span>', obj.get_status_display())

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:project_id>/trigger/",
                self.admin_site.admin_view(self.trigger_character_annotation_view),
                name="character_annotation_trigger",
            ),
        ]
        return custom_urls + urls

    def trigger_character_annotation_view(self, request, project_id):
        project = get_object_or_404(CharacterAnnotationProject, pk=project_id)

        medias = project.asset.medias.all()
        if not medias.exists():
            # [修改] 使用 f-string 配合 gettext，避开下划线别名
            msg = gettext("资产《{}》下没有媒体文件，无法启动。").format(project.asset.title)
            messages.warning(request, msg)
            return redirect("admin:workflow_characterannotationproject_changelist")

        jobs_created = 0
        for media in medias:
            _, created = CharacterAnnotationJob.objects.get_or_create(project=project, media=media)
            if created:
                jobs_created += 1

        if jobs_created > 0:
            logger.info(f"Created {jobs_created} jobs for project {project.id}")

        start_character_annotation_task.delay(str(project.id))

        # [修改] 同样处理成功消息
        msg_ok = gettext("已成功为项目《{}》派发识别任务，请观察状态流转。").format(project.name)
        messages.success(request, msg_ok)

        return redirect("admin:workflow_characterannotationproject_changelist")
