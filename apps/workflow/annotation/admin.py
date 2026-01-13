import json
import logging

from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import Http404
from django.middleware.csrf import get_token
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from apps.media_assets.models import Asset, Media

from .forms import AnnotationProjectForm
from .jobs import AnnotationJob
from .projects import AnnotationProject

logger = logging.getLogger(__name__)


@admin.register(AnnotationProject)
class AnnotationProjectAdmin(ModelAdmin):
    form = AnnotationProjectForm

    # =========================================================================
    # 1. 列表视图 (Changelist) 配置
    # =========================================================================

    # [修改] 移除 valid_job_count，加入 enter_project_action
    list_display = ("name", "asset_link", "status", "created", "enter_project_action")
    list_display_links = ("name",)  # 点击名称也可以进入
    list_filter = ("status",)
    search_fields = ("name", "id")
    list_per_page = 20

    # =========================================================================
    # 2. 新建/详情视图 (Add/Change) 配置
    # =========================================================================

    # [关键配置] 专门用于 "新建页面" 的字段配置
    # 仅展示核心 4 项，Status 被隐藏（自动使用默认值 PENDING）
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("name", "asset", "description"),
            },
        ),
    )

    # 详情页配置 (虽然主要被 React 接管，但保持定义是个好习惯)
    fieldsets = (("基本信息", {"fields": ("name", "status", "description")}),)

    # =========================================================================
    # [核心修复] 覆盖 save_model，在项目创建后自动初始化 Job
    # =========================================================================
    def save_model(self, request, obj, form, change):
        """
        重写 save_model。如果项目是新建的 (not change)，则初始化 AnnotationJob。
        """
        is_newly_created = not change

        # 1. 先保存 Project 对象 (确保 obj.id 存在)
        super().save_model(request, obj, form, change)

        # 2. 如果是新建项目，则创建 Annotation Job
        if is_newly_created:
            self.create_jobs_for_project(obj)

    def create_jobs_for_project(self, project: AnnotationProject):
        """
        根据关联的 Asset，为每个 Media 文件创建 AnnotationJob。
        """
        if not project.asset:
            logger.warning(f"Project {project.id} saved without an Asset. Cannot create jobs.")
            return

        # 获取 Asset 下的所有 Media 文件，按 sequence_number 排序
        # 假设 Media 模型有一个指向 Asset 的外键，related_name 默认为 media_set
        media_files = Media.objects.filter(asset=project.asset).order_by("sequence_number")

        if not media_files.exists():
            logger.warning(f"Asset {project.asset.id} has no Media files. No jobs created for project {project.id}.")
            return

        jobs_to_create = []
        for media in media_files:
            # 创建 AnnotationJob 实例
            job = AnnotationJob(project=project, media=media, status=AnnotationJob.STATUS.PENDING)  # 默认状态
            jobs_to_create.append(job)

        with transaction.atomic():
            # 批量创建所有 Job，提高效率
            AnnotationJob.objects.bulk_create(jobs_to_create)

        logger.info(f"Successfully created {len(jobs_to_create)} AnnotationJobs for new project {project.id}.")

        # [可选] 更新项目状态为 PROCESSING，因为它现在包含待处理的任务
        if len(jobs_to_create) > 0 and project.status != "PROCESSING":
            project.status = "PROCESSING"
            project.save(update_fields=["status"])
            logger.info(f"Updated project {project.id} status to PROCESSING.")

    # =========================================================================
    # 3. 视图逻辑重写
    # =========================================================================

    # [修改] add_view: 劫持新建页面
    def add_view(self, request, form_url="", extra_context=None):
        # 1. 经典模式判断 (保持不变)
        if request.GET.get("mode") == "classic" or request.method == "POST":
            self.change_form_template = None
            return super().add_view(request, form_url, extra_context)

        # 2. React 模式

        # [关键修复] 获取 Admin 全局上下文 (包含 Sidebar, User Info, Navigation 等)
        context = self.admin_site.each_context(request)

        # 合并传入的 extra_context
        if extra_context:
            context.update(extra_context)

        # 注入页面特定信息
        context.update(
            {
                "title": "新建标注项目",
                "subtitle": None,
                "is_popup": False,
                "to_field": None,
                # 注入 opts 以便模板正确生成面包屑和权限标记
                "opts": self.model._meta,
                "has_add_permission": self.has_add_permission(request),
            }
        )

        # ... (Asset 数据准备逻辑保持不变) ...
        assets = list(Asset.objects.values("id", "title").order_by("-created"))
        asset_options = [{"value": str(a["id"]), "label": a["title"]} for a in assets]

        server_context = {
            "assets": asset_options,
            "csrfToken": get_token(request),
            "urls": {
                "import_api": reverse("workflow:annotation:handle-import-project"),
            },
        }

        context["server_data_json"] = json.dumps(server_context, cls=DjangoJSONEncoder)

        # 使用修改后的模板
        return TemplateResponse(request, "admin/workflow/project/annotation/import_wizard.html", context)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        # 详情时使用 React Dashboard 模板
        self.change_form_template = "admin/workflow/project/annotation/dashboard.html"
        return self.render_react_dashboard(request, object_id, extra_context)

    # =========================================================================
    # 4. 辅助渲染函数
    # =========================================================================

    @admin.display(description="操作")
    def enter_project_action(self, obj):
        """
        列表页的大按钮，引导用户进入 Dashboard
        """
        url = reverse("admin:workflow_annotationproject_change", args=[obj.pk])
        return format_html(
            '<a href="{}" class="font-medium text-blue-600 hover:text-blue-800 flex items-center gap-1">'
            "<span>进入项目</span> &rarr;"
            "</a>",
            url,
        )

    @admin.display(description="关联资产")
    def asset_link(self, obj):
        """显示关联资产名称"""
        return obj.asset.title if obj.asset else "-"

    def render_react_dashboard(self, request, object_id, extra_context=None):
        """
        构建 React 所需的 JSON 上下文
        """
        context = extra_context or {}
        context.update({"show_save": False, "show_save_and_continue": False, "show_save_and_add_another": False})

        obj_id = unquote(object_id)
        project = self.get_object(request, obj_id)
        if project is None:
            raise Http404(f"AnnotationProject {obj_id} not found")

        # --- 数据准备 ---
        audit_data = {}
        report_loaded = False

        if project.annotation_audit_report:
            try:
                with project.annotation_audit_report.open("r") as f:
                    audit_data = json.load(f)
                    report_loaded = True
            except Exception as e:
                logger.error(f"Failed to load audit report: {e}")

        jobs_queryset = AnnotationJob.objects.filter(project=project).order_by("media__sequence_number")

        job_items = []
        for job in jobs_queryset:
            download_url = None
            # [Refinery适配] JSONField 模式下暂不支持直接文件下载，后续可改为 API 导出链接
            # download_url = ...

            job_items.append(
                {
                    "id": str(job.id),
                    "name": str(job),
                    "media_title": job.media.title,
                    "status": job.status,
                    "status_display": job.get_status_display(),
                    # 项目管理：创建时间和最后修改时间
                    "created_at": job.created.strftime("%Y-%m-%d %H:%M"),
                    "updated_at": job.modified.strftime("%Y-%m-%d %H:%M"),
                    # API 链接
                    "workbench_url": reverse("workflow:annotation:annotation_workbench", args=[job.id]),
                    "download_url": download_url,
                }
            )

        server_context = {
            "meta": {
                "id": str(project.id),
                "name": project.name,
                "status": project.status,
                "has_report": report_loaded,
                "valid_job_count": project.jobs.count(),
            },
            "dashboard": {
                "engineering": audit_data.get("engineering_stats", {}),
                "semantic": audit_data.get("semantic_audit", {}),
                "technical": audit_data.get("technical_audit", {}),
            },
            "jobs": job_items,
            "urls": {
                "trigger_audit": reverse("workflow:annotation:trigger-project-audit", args=[project.id]),
                "export_project": reverse("workflow:annotation:export-project", args=[project.id]),
            },
        }

        context["server_data_json"] = json.dumps(server_context, cls=DjangoJSONEncoder)
        return super().changeform_view(request, str(object_id), form_url="", extra_context=context)
