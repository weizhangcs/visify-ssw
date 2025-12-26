# apps/workflow/scene_orchestration/views.py
import json
import logging

import django
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.workflow.annotation.projects import AnnotationProject

from .services.services import OrchestrationService

logger = logging.getLogger(__name__)

# =========================================================================
# [新增] 场景编排工作台 (Orchestration Workbench)
# =========================================================================


@login_required
def annotation_orchestration_entry(request, project_id):
    """
    [Page] 编排工作台全屏入口
    """
    project = get_object_or_404(AnnotationProject, pk=project_id)

    # 构造前端所需的上下文
    context_data = {
        "project_id": str(project.id),
        "project_name": project.name,
        "urls": {
            # API 地址
            "load_data": reverse("workflow:scene_orchestration:orchestration_data", args=[project.id]),
            "save_data": reverse("workflow:scene_orchestration:orchestration_save", args=[project.id]),
            "back": reverse("admin:workflow_annotationproject_change", args=[project.id]),
        },
        "csrfToken": django.middleware.csrf.get_token(request),
    }

    return render(
        request,
        "admin/workflow/project/scene_orchestration/orchestration.html",
        {"project_name": project.name, "server_context": context_data},
    )


@login_required
def orchestration_get_data_api(request, project_id):
    """
    [API] 获取编排所需的全量数据
    """
    project = get_object_or_404(AnnotationProject, pk=project_id)
    try:
        # Service 负责组装一切 (Scenes + Graph)
        payload = OrchestrationService.get_orchestration_source_data(project)

        return JsonResponse({"status": "success", "data": payload})
    except Exception as e:
        logger.error(f"Orchestration Data Error: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@require_POST
@login_required
def orchestration_save_api(request, project_id):
    """
    [API] 保存编排图谱
    """

    project = get_object_or_404(AnnotationProject, pk=project_id)
    try:
        data = json.loads(request.body)

        # 调用 Service 保存
        OrchestrationService.save_orchestration_graph(project, data)

        return JsonResponse({"status": "success", "message": "Saved successfully"})
    except Exception as e:
        logger.error(f"Orchestration Save Error: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)
