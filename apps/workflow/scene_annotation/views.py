from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse

from .models import SceneAnnotationProject
from .services.service import SceneAnnotationService


def trigger_scene_annotation_view(request, project_id):
    """
    触发场景标注任务 (View Layer - Thin Shell)
    """
    # 1. 权限与对象校验 (View 的职责)
    project = get_object_or_404(SceneAnnotationProject, pk=project_id)

    # 2. 简单的业务前置检查 (可选，为了 UX 更好，可以保留在 View，也可以下沉)
    if not project.asset.medias.exists():
        messages.error(request, f"资产 [{project.asset.title}] 下未找到任何媒体文件。")
        return HttpResponseRedirect(reverse("admin:workflow_sceneannotationproject_changelist"))

    try:
        # 3. 调用 Service 执行核心逻辑
        count = SceneAnnotationService.launch_project(project_id=str(project.id))

        # 4. 根据结果返回消息
        if count > 0:
            messages.success(request, f"已成功启动 {count} 个场景切片任务。")
        else:
            messages.info(request, "所有媒体文件均已在处理中或已完成，无新任务启动。")

    except Exception as e:
        # 兜底错误处理
        messages.error(request, f"启动失败: {str(e)}")

    return HttpResponseRedirect(reverse("admin:workflow_sceneannotationproject_changelist"))
