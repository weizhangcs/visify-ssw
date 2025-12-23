# apps/workflow/scene_annotation/views.py
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse

from .models import SceneAnnotationJob, SceneAnnotationProject
from .tasks import run_scene_annotation_pipeline


def trigger_scene_annotation_view(request, project_id):
    project = get_object_or_404(SceneAnnotationProject, pk=project_id)
    medias = project.asset.medias.all().order_by("sequence_number")

    if not medias.exists():
        messages.error(request, f"资产 [{project.asset.title}] 下未找到任何媒体文件。")
        return HttpResponseRedirect(reverse("admin:workflow_sceneannotationproject_changelist"))

    # 1. 遍历所有媒体，批量创建 Job 并分发
    for media in medias:
        # 遵循 FSM 范式：仅创建，不显式赋值 status（依赖模型 default）
        SceneAnnotationJob.objects.get_or_create(project=project, media=media)

        # 2. 发起异步任务
        run_scene_annotation_pipeline.delay(
            project_id=project.id,
            media_id=str(media.id),
            video_path=media.get_best_playback_url(),
            ass_path=media.source_subtitle.path if media.source_subtitle else "",
        )

    # 3. 更新 Project 状态
    project.status = "PROCESSING"
    project.save()

    messages.success(request, f"成功为 {medias.count()} 个媒体文件启动解析流程。")
    return HttpResponseRedirect(reverse("admin:workflow_sceneannotationproject_changelist"))
