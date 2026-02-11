import logging

from django.contrib import admin, messages
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .models import DubbingAtomPipeline, DubbingAtomRule, DubbingAtomUnit, DubbingSession
from .scheduler import DubbingAtomScheduler

logger = logging.getLogger(__name__)


@admin.register(DubbingAtomUnit)
class DubbingAtomUnitAdmin(ModelAdmin):
    list_display = ("name", "slug", "execution_mode", "resource_class")


@admin.register(DubbingAtomRule)
class DubbingAtomRuleAdmin(ModelAdmin):
    list_display = ("name", "slug", "step_count", "mode", "modified")


@admin.register(DubbingSession)
class DubbingSessionAdmin(ModelAdmin):
    list_display = ("id", "material_link", "created")

    def material_link(self, obj):
        if obj.material:
            return f"{obj.material.media.title} ({obj.material.id})"
        return "-"

    material_link.short_description = "源素材"


@admin.register(DubbingAtomPipeline)
class DubbingAtomPipelineAdmin(ModelAdmin):
    list_display = ("name", "status_badge", "rule", "session_link", "run_action", "created")
    list_filter = ("status", "rule")
    actions = ["start_selected_pipelines"]

    # [优化] 将系统自动维护的字段设为只读，避免人工误改
    readonly_fields = ("metrics", "error_log", "stop_point", "created", "modified", "target_id")

    fieldsets = (
        (
            "基本信息",
            {
                "fields": ("name", "rule", "session", "status"),
            },
        ),
        (
            "执行监控",
            {
                "classes": ("collapse",),
                "fields": ("metrics", "error_log", "stop_point", "target_id", "created", "modified"),
            },
        ),
    )

    def session_link(self, obj):
        if obj.session:
            return obj.session.id
        return "-"

    session_link.short_description = "关联会话"

    def status_badge(self, obj):
        colors = {
            "PENDING": "gray",
            "RUNNING": "blue",
            "SUCCESS": "green",
            "FAILED": "red",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            f'<span class="px-2 py-1 rounded text-xs font-bold bg-{color}-100 text-{color}-800">{obj.get_status_display()}</span>'  # noqa: E501
        )

    status_badge.short_description = "状态"

    def run_action(self, obj):
        if obj.status in ["PENDING", "FAILED", "STOPPED"]:
            return format_html('<a class="button" href="{}">🚀 启动</a>', f"start/{obj.id}/")
        return "-"

    run_action.short_description = "操作"

    # 自定义 URL 处理启动请求
    def get_urls(self):
        from django.shortcuts import redirect
        from django.urls import path

        def start_pipeline_view(request, pipeline_id):
            try:
                logger.info(f"[DubbingAdmin] 正在触发流水线启动: {pipeline_id}")
                DubbingAtomScheduler.start_pipeline(pipeline_id)
                self.message_user(request, f"流水线 {pipeline_id} 已启动", messages.SUCCESS)
            except Exception as e:
                logger.error(f"[DubbingAdmin] 启动失败: {e}", exc_info=True)
                self.message_user(request, f"启动失败: {e}", messages.ERROR)
            return redirect("admin:dubbing_dubbingatompipeline_changelist")

        urls = super().get_urls()
        custom_urls = [path("start/<str:pipeline_id>/", self.admin_site.admin_view(start_pipeline_view))]
        return custom_urls + urls

    @admin.action(description="批量启动流水线")
    def start_selected_pipelines(self, request, queryset):
        for p in queryset:
            if p.status not in ["RUNNING", "SUCCESS"]:
                try:
                    logger.info(f"[DubbingAdmin] 批量触发流水线: {p.id}")
                    DubbingAtomScheduler.start_pipeline(str(p.id))
                    self.message_user(request, f"流水线 {p.name} 已触发", messages.SUCCESS)
                except Exception as e:
                    logger.error(f"[DubbingAdmin] 批量启动失败 {p.name}: {e}", exc_info=True)
                    self.message_user(request, f"流水线 {p.name} 启动失败: {e}", messages.ERROR)

    def save_model(self, request, obj, form, change):
        # 自动填充 target_id (关联 Session ID)，无需人工复制粘贴
        if obj.session and not obj.target_id:
            obj.target_id = str(obj.session.id)
        super().save_model(request, obj, form, change)
