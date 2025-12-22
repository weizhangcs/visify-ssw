# 文件路径: apps/workflow/inference/admin.py

import json
import logging

from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.core.serializers.json import DjangoJSONEncoder
from django.http import Http404, HttpRequest
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from .forms import InferenceProjectForm
from .projects import InferenceJob, InferenceProject

logger = logging.getLogger(__name__)


# --- Tab 导航定义 (保留 Tab 2) ---
def get_inference_project_tabs(request: HttpRequest) -> list[dict]:
    resolver = request.resolver_match
    if not (resolver and resolver.view_name.startswith("admin:workflow_inferenceproject_")):
        return []

    object_id = resolver.kwargs.get("object_id")
    if not object_id:
        return []

    current_view_name = resolver.view_name
    default_change_view_name = "admin:workflow_inferenceproject_change"

    tab_items = []
    if object_id:
        tab_items = [
            {
                # 修改标题，体现功能合并
                "title": "第一步：识别与部署",
                "link": reverse("admin:workflow_inferenceproject_tab_1_facts", args=[object_id]),
                "active": current_view_name
                in ["admin:workflow_inferenceproject_tab_1_facts", default_change_view_name],
            },
            {
                # 保留 Tab 2，标记为预留
                "title": "第二步：高级功能 (预留)",
                "link": reverse("admin:workflow_inferenceproject_tab_2_rag", args=[object_id]),
                "active": current_view_name == "admin:workflow_inferenceproject_tab_2_rag",
            },
        ]

    return [
        {
            "models": [{"name": "workflow.inferenceproject", "detail": True}],
            "items": tab_items,
        }
    ]


class InferenceJobInline(TabularInline):
    model = InferenceJob
    extra = 0
    can_delete = False
    hide_title = True
    list_display = ("job_type", "status", "cloud_task_id", "created")
    readonly_fields = ("job_type", "status", "cloud_task_id", "created", "modified", "input_params")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(InferenceProject)
class InferenceProjectAdmin(ModelAdmin):
    form = InferenceProjectForm
    list_display = ("name", "asset", "status", "created", "view_current_project", "go_to_annotation")
    list_display_links = ("name",)
    list_per_page = 20
    search_fields = ("name", "annotation_project__name")

    add_fieldsets = ((None, {"fields": ("name", "description", "annotation_project")}),)
    fieldsets = ((None, {"fields": ("name", "description", "annotation_project")}),)

    # inlines = [InferenceJobInline]

    def get_urls(self):
        urls = super().get_urls()

        def get_url_name(view_name):
            return f"{self.model._meta.app_label}_{self.model._meta.model_name}_{view_name}"

        custom_urls = [
            path(
                "<uuid:object_id>/change/tab-1-facts/",
                self.admin_site.admin_view(self.tab_1_facts_view),
                name=get_url_name("tab_1_facts"),
            ),
            # 保留 Tab 2 URL
            path(
                "<uuid:object_id>/change/tab-2-rag/",
                self.admin_site.admin_view(self.tab_2_rag_view),
                name=get_url_name("tab_2_rag"),
            ),
        ]
        return custom_urls + urls

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return self.tab_1_facts_view(request, object_id, extra_context)

    def add_view(self, request, form_url="", extra_context=None):
        self.change_form_template = None
        return super().add_view(request, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        if not change:
            annotation_project = form.cleaned_data["annotation_project"]
            obj.asset = annotation_project.asset
        super().save_model(request, obj, form, change)

    # --- 视图逻辑 ---

    def tab_1_facts_view(self, request, object_id, extra_context=None):
        """
        [Tab 1] 事实提取 + RAG 部署入口
        """
        context = extra_context or {}
        context.update({"show_save": False, "show_save_and_continue": False, "show_save_and_add_another": False})

        # [核心修复] 在调用 unquote 之前，显式将 UUID 对象转换为字符串。
        object_id_str = str(object_id)  # <--- [这是关键]

        # [修复 1] 规范化 object_id (现在输入确保是字符串)
        obj_id = unquote(object_id_str)

        # [修复 2] 安全获取对象
        project = self.get_object(request, obj_id)

        if project is None:
            # 如果对象不存在（可能被删了，或者 URL 输错了），直接抛出标准的 404 页面
            raise Http404(f"InferenceProject with ID {obj_id} does not exist.")

        # 1. 读取角色矩阵 (逻辑不变)
        character_data = {"all_characters": [], "importance_scores": {}, "min_score": 0, "max_score": 0}
        metrics_loaded = False
        error_msg = None

        try:
            anno_proj = project.annotation_project
            # [适配] 检查新字段 annotation_audit_report
            if anno_proj and anno_proj.annotation_audit_report:
                with anno_proj.annotation_audit_report.open("r") as f:
                    audit_data = json.load(f)

                    # [数据映射] Audit Report (New) -> Frontend Props (Old)
                    # 路径: semantic_audit -> character_roster
                    roster = audit_data.get("semantic_audit", {}).get("character_roster", [])

                    if roster:
                        # 提取名字列表
                        all_chars = [r["name"] for r in roster if r.get("name")]

                        # 提取权重字典 { "Name": score }
                        # 现在的 weight_score 是归一化后的分值 (0.0 - 4.0 左右)
                        scores = {r["name"]: r.get("weight_score", 0) for r in roster if r.get("name")}

                        if all_chars:
                            character_data["all_characters"] = all_chars
                            character_data["importance_scores"] = scores

                            # 计算极值，用于前端热力图渲染
                            all_values = list(scores.values())
                            if all_values:
                                character_data["min_score"] = min(all_values)
                                character_data["max_score"] = max(all_values)

                            metrics_loaded = True
                    else:
                        error_msg = "审计报告中未发现角色数据 (可能无人名标注)。"
            else:
                error_msg = "未找到‘产出物审计报告’。请先在标注项目中运行审计。"

        except Exception as e:
            logger.error(f"Error loading audit report: {e}", exc_info=True)
            error_msg = f"读取数据失败: {str(e)}"

        # 2. 历史列表 (保持不变)
        # [核心修复] 查询所有相关类型的 Job
        jobs_list_queryset = InferenceJob.objects.filter(
            project=project,
            # 过滤出 FACTS 和 RAG_DEPLOYMENT 两种类型的 Job
            job_type__in=[InferenceJob.TYPE.FACTS, InferenceJob.TYPE.RAG_DEPLOYMENT],
        ).order_by(
            "-created"
        )  # 按创建时间倒序排列

        # 将 QuerySet 转换为列表
        jobs_list = list(jobs_list_queryset)

        history_items = []

        for job in jobs_list:
            input_data = job.input_params if isinstance(job.input_params, dict) else {}

            history_items.append(
                {
                    "id": str(job.id),
                    "typeCode": job.job_type,
                    "jobType": job.get_job_type_display(),
                    "status": job.status,
                    "statusDisplay": job.get_status_display(),
                    "created": job.created.strftime("%Y-%m-%d %H:%M"),
                    "input": input_data,
                    "output": {},
                }
            )

        context["server_data_json"] = json.dumps(
            {
                "meta": {"metricsLoaded": metrics_loaded, "errorMsg": error_msg},
                "character_data": character_data,
                "items": history_items,
                "urls": {"submit": reverse("workflow:inference_trigger_cloud_facts", args=[project.id])},
            },
            cls=DjangoJSONEncoder,
        )

        self.fieldsets = self.fieldsets
        self.change_form_template = "admin/workflow/project/inference/tab_1_facts.html"
        return super().changeform_view(request, str(object_id), form_url="", extra_context=context)

    def tab_2_rag_view(self, request, object_id, extra_context=None):
        """
        [Tab 2] 预留视图 (Reserves)
        """
        context = extra_context or {}
        context.update({"show_save": False, "show_save_and_continue": False, "show_save_and_add_another": False})

        # 仅传递简单的占位信息，不执行重逻辑
        context["server_data_json"] = json.dumps({"message": "此模块已预留，等待后续规划。"}, cls=DjangoJSONEncoder)

        self.fieldsets = self.fieldsets
        self.change_form_template = "admin/workflow/project/inference/tab_2_rag.html"
        return super().changeform_view(request, str(object_id), form_url="", extra_context=context)

    # --- 辅助方法 ---
    @admin.display(description="操作")
    def view_current_project(self, obj):
        url = reverse("admin:workflow_inferenceproject_change", args=[obj.pk])
        return format_html('<a href="{}" class="button">进入项目</a>', url)

    @admin.display(description="关联标注项目")
    def go_to_annotation(self, obj):
        if obj.annotation_project:
            url = reverse("admin:workflow_annotationproject_change", args=[obj.annotation_project.pk])
            return format_html('<a href="{}" class="button">返回标注</a>', url)
        return "N/A"
