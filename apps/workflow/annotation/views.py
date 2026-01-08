# apps/workflow/annotation/views.py

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .jobs import AnnotationJob
from .projects import AnnotationProject
from .services.annotation_service import AnnotationService
from .services.audit_service import ArtifactAuditService
from .services.export_project_service import ProjectExportService
from .services.import_project_service import ProjectImportService

logger = logging.getLogger(__name__)


@login_required
def annotation_workbench_entry(request, job_id):
    job = get_object_or_404(AnnotationJob, pk=job_id)

    # [状态联动] 进入标注台时的状态流转
    job_status_changed = False

    if job.status == "PENDING":
        job.start_annotation()
        job_status_changed = True
    elif job.status == "COMPLETED":
        # 如果已完成的任务再次被打开，视为“修订”
        job.revise()  # 状态变为 REVISING，并触发数据备份
        job_status_changed = True

    if job_status_changed:
        job.save()
        # 如果任务状态回退了，项目状态也应该回退 (不再是已完成)
        if job.project.status == "COMPLETED":
            job.project.status = "PROCESSING"
            job.project.save(update_fields=["status"])

    server_data = {}  # [修改] 默认类型改为字典

    # 1. 加载数据并注入
    try:
        media_annotation = AnnotationService.load_annotation(job)

        # [核心重构] 统一数据组装
        # 1.1 基础标注数据
        server_data = media_annotation.model_dump()

    except Exception as e:
        logger.error(f"Data Load Error for Job {job.id}: {e}", exc_info=True)
        server_data = {"error": str(e)}

    # 5. 返回路径
    try:
        return_url = reverse("admin:workflow_annotationproject_change", args=[job.project.id])
    except Exception:
        return_url = "/admin/"

    context = {
        # 仅保留 View 层负责的路由信息和统一的数据包
        "return_url": return_url,
        "server_data": server_data,  # [修改] 传递 Dict
        # [Fix] 模板中的 {% url %} 标签需要 job_id 参数，否则会报 NoReverseMatch
        "job_id": job.id,
        "project_id": job.project.id,
    }

    return render(request, "admin/workflow/project/annotation/workbench.html", context)


@require_POST
def annotation_save_api(request, job_id):
    try:
        job = get_object_or_404(AnnotationJob, pk=job_id)
        payload = json.loads(request.body)

        AnnotationService.save_annotation(job, payload, user_id=str(request.user.id))

        return JsonResponse({"status": "success", "message": "Saved successfully"})
    except Exception as e:
        logger.error(f"Save failed for Job {job_id}: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@require_GET
def trigger_audit(request, project_id):
    project = AnnotationProject.objects.get(id=project_id)
    report = ArtifactAuditService.run_project_audit(project)
    return JsonResponse(report)


def export_project_view(request, project_id):
    project = get_object_or_404(AnnotationProject, id=project_id)

    try:
        # [Refactor] 调用 Service 进行导出，而不是 Model
        content_file = ProjectExportService.export_project_package(project)
    except Exception as e:
        return HttpResponse(f"导出失败: {str(e)}", status=500)

    # 返回文件流
    response = HttpResponse(content_file, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{content_file.name}"'  # noqa: E702
    return response


def handle_import_project(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Method not allowed"}, status=405)

    try:
        zip_file = request.FILES.get("import_file")
        asset_id = request.POST.get("asset_id")
        project_name = request.POST.get("name")

        if not zip_file or not asset_id:
            return JsonResponse({"success": False, "message": "缺少文件或资产ID"}, status=400)

        new_project = ProjectImportService.execute_import(
            json_file=zip_file, target_asset_id=asset_id, project_name_override=project_name
        )

        redirect_url = reverse("admin:workflow_annotationproject_change", args=[new_project.id])
        return JsonResponse({"success": True, "redirect_url": redirect_url})

    except ValueError as e:
        return JsonResponse({"success": False, "message": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "message": f"系统错误: {str(e)}"}, status=500)
