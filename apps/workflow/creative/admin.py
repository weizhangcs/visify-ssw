# apps/workflow/creative/admin.py

import json
import logging

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .forms import CreativeProjectForm
from .models import CreativeProject

logger = logging.getLogger(__name__)


# --- 1. Tab 导航定义 ---
def get_creative_project_tabs(request: HttpRequest) -> list[dict]:
    resolver = request.resolver_match
    if not (resolver and resolver.view_name.startswith("admin:workflow_creativeproject_")):
        return []

    object_id = resolver.kwargs.get("object_id")
    if not object_id:
        return []

    current_view = resolver.view_name

    return [
        {
            "models": [{"name": "workflow.creativeproject", "detail": True}],
            "items": [
                {
                    "title": "🎬 导演驾驶舱 (Config)",
                    "link": reverse("admin:workflow_creativeproject_change", args=[object_id]),
                    "active": current_view == "admin:workflow_creativeproject_change",
                },
                {
                    "title": "📺 进度监视器 (Monitor)",
                    "link": reverse("admin:workflow_creativeproject_tab_monitor", args=[object_id]),
                    "active": current_view == "admin:workflow_creativeproject_tab_monitor",
                },
            ],
        }
    ]


@admin.register(CreativeProject)
class CreativeProjectAdmin(ModelAdmin):
    form = CreativeProjectForm
    list_display = ("name", "asset", "status_badge", "created", "action_open_monitor")
    # [核心修复] 增加分页
    list_per_page = 20
    # search_fields = ("name", "inference_project__name", "asset__title")
    # autocomplete_fields = ["inference_project"]

    readonly_fields = ("status",)

    def status_badge(self, obj):
        return obj.status

    status_badge.short_description = "状态"

    # --- URL 路由 ---
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<uuid:object_id>/change/tab-monitor/",
                self.admin_site.admin_view(self.render_monitor_tab),
                name="workflow_creativeproject_tab_monitor",
            ),
        ]
        return custom_urls + urls

    # --- 核心：字段显示控制 ---
    def get_fieldsets(self, request, obj=None):
        if obj is None:
            # [Add View] 显示创建表单
            return (
                (
                    None,
                    {
                        "fields": ("name", "inference_project", "project_type"),
                        "description": "请填写项目名称并关联推理项目。系统将自动关联对应的媒资。",
                    },
                ),
            )
        # [Change View] 隐藏所有字段 (交给 React)
        return ((None, {"fields": ()}),)

    # --- 核心：视图与模板控制 ---

    def add_view(self, request, form_url="", extra_context=None):
        # [强制重置] Add 模式必须用默认模板，否则会加载 React 导致 404
        self.change_form_template = None
        return super().add_view(request, form_url, extra_context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}

        # [UI] 隐藏按钮
        extra_context["show_save"] = False
        extra_context["show_save_and_continue"] = False
        extra_context["show_save_and_add_another"] = False

        if object_id:
            project = self.get_object(request, object_id)

            assets = {
                "source_language": project.asset.language if project.asset else "zh-CN",
                "narration": {
                    "exists": bool(project.narration_script_file),
                    "name": str(project.narration_script_file),
                },
                "localize": {"exists": bool(project.localized_script_file), "name": str(project.localized_script_file)},
                "audio": {"exists": bool(project.dubbing_script_file), "name": str(project.dubbing_script_file)},
            }

            extra_context["server_data_json"] = json.dumps(
                {
                    "project_id": str(project.id),
                    "project_name": project.name,
                    "assets": assets,
                    "initial_config": project.auto_config or {},
                },
                ensure_ascii=False,
            )

            # [强制指定] Change 模式必须加载 React 模板
            self.change_form_template = "admin/workflow/project/creative/director_tab.html"

        return super().change_view(request, object_id, form_url, extra_context)

    def render_monitor_tab(self, request, object_id, extra_context=None):
        context = extra_context or {}
        project = self.get_object(request, object_id)

        context["show_save"] = False
        context["show_save_and_continue"] = False
        context["show_save_and_add_another"] = False

        # 1. 进度
        status_weights = {
            "CREATED": 5,
            "NARRATION_RUNNING": 15,
            "NARRATION_COMPLETED": 30,
            "LOCALIZATION_RUNNING": 40,
            "LOCALIZATION_COMPLETED": 50,
            "AUDIO_RUNNING": 60,
            "AUDIO_COMPLETED": 75,
            "EDIT_RUNNING": 85,
            "EDIT_COMPLETED": 95,
            "SYNTHESIS_RUNNING": 98,
            "COMPLETED": 100,
            "FAILED": 100,
        }
        context["progress_percent"] = status_weights.get(project.status, 5)
        context["project"] = project
        context["is_running"] = project.status not in ["COMPLETED", "FAILED"]

        # 2. 解说词解析
        script_data = []
        has_translation = False
        target_file = project.localized_script_file if project.localized_script_file else project.narration_script_file

        if target_file:
            try:
                with target_file.open("r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        raw_list = data.get("narration_script") or data.get("narration") or []
                    else:
                        raw_list = data if isinstance(data, list) else []

                    for item in raw_list:
                        main_text = (item.get("narration") or "").strip()
                        source_text = (item.get("narration_source") or "").strip()
                        if project.localized_script_file and source_text:
                            script_data.append({"source": source_text, "target": main_text})
                            has_translation = True
                        else:
                            script_data.append({"source": main_text, "target": ""})
            except Exception as e:
                logger.error(f"Script Parse Error: {e}")
                script_data = [{"source": f"数据异常: {str(e)}", "target": ""}]
        else:
            status_hint = "⏳ 等待生成..." if context["is_running"] else "❌ 未找到脚本文件"
            script_data = [{"source": status_hint, "target": ""}]

        context["script_lines"] = script_data
        context["has_translation"] = has_translation

        # 3. 配音解析
        audio_list = []
        if project.dubbing_script_file:
            try:
                with project.dubbing_script_file.open("r") as f:
                    data = json.load(f)
                    segments = data.get("dubbing_script") or data.get("dubbing") or []
                    if not isinstance(segments, list):
                        segments = []

                    for seg in segments:
                        local_path = seg.get("local_audio_path")
                        text_preview = (seg.get("narration") or "")[:20] + "..."

                        if local_path:
                            # [核心修复] 手动拼接 Nginx 的绝对地址
                            # 1. 组合相对路径: "/media/" + "creative/..."
                            relative_url = f"{settings.MEDIA_URL}{local_path}"

                            # 2. 组合绝对路径: "http://IP:9999" + "/media/..."
                            # 确保去除 base 末尾的 / 防止双斜杠
                            base_url = settings.LOCAL_MEDIA_URL_BASE.rstrip("/")
                            full_url = f"{base_url}{relative_url}"

                            audio_list.append({"name": text_preview, "url": full_url})
            except Exception as e:
                logger.error(f"Audio Parse Error: {e}")

        context["audio_list"] = audio_list

        # [强制指定] Monitor 模板
        self.change_form_template = "admin/workflow/project/creative/monitor.html"
        return super().changeform_view(request, str(object_id), extra_context=context)

    # --- 辅助方法 ---
    @admin.display(description="监视器")
    def action_open_monitor(self, obj):
        url = reverse("admin:workflow_creativeproject_tab_monitor", args=[obj.pk])
        return format_html('<a href="{}" class="button">查看进度</a>', url)

    def save_model(self, request, obj, form, change):
        if not change and obj.inference_project and not obj.asset_id:
            obj.asset = obj.inference_project.asset
        super().save_model(request, obj, form, change)
