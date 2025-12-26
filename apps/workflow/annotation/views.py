# apps/workflow/annotation/views.py

import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.workflow.character_annotation.models import CharacterAnnotationJob
from apps.workflow.common.baseJob import BaseJob
from apps.workflow.transcoding.jobs import TranscodingJob

from .jobs import AnnotationJob
from .projects import AnnotationProject
from .services.annotation_service import AnnotationService
from .services.import_service import ProjectImportService

logger = logging.getLogger(__name__)


def _build_full_url(url_path):
    if not url_path:
        return ""
    if url_path.startswith("http"):
        return url_path

    base = getattr(settings, "LOCAL_MEDIA_URL_BASE", "").rstrip("/")
    path = url_path.lstrip("/")
    return f"{base}/{path}"


@login_required
def annotation_workbench_entry(request, job_id):
    job = get_object_or_404(AnnotationJob, pk=job_id)

    if job.status == "PENDING":
        job.start_annotation()
        job.save()

    video_url = ""
    server_data = {}  # [修改] 默认类型改为字典
    character_list = []

    # 1. 计算最佳视频播放地址
    try:
        transcoding_job = (
            TranscodingJob.objects.filter(media=job.media, status="COMPLETED").order_by("-modified").first()
        )

        if transcoding_job and transcoding_job.output_url:
            video_url = _build_full_url(transcoding_job.output_url)
        elif job.media.source_video:
            video_url = _build_full_url(job.media.source_video.url)

        logger.info(f"Resolved Video URL for Job {job_id}: {video_url}")
    except Exception as e:
        logger.error(f"Video URL Resolution Error: {e}")
        if hasattr(job.media, "source_video") and job.media.source_video:
            video_url = job.media.source_video.url

    # 2. 加载数据并注入
    try:
        media_annotation = AnnotationService.load_annotation(job)
        if video_url:
            media_annotation.source_path = video_url

        # [核心修改] 使用 model_dump() 返回 Python 字典
        # 让 Django 模板的 json_script 标签去处理序列化和转义
        server_data = media_annotation.model_dump()

    except Exception as e:
        logger.error(f"Data Load Error for Job {job.id}: {e}", exc_info=True)
        server_data = {"error": str(e)}

    # 3. 获取波形图
    waveform_url = None
    if job.media.waveform_data:
        waveform_url = _build_full_url(job.media.waveform_data.url)

    # 4. 获取全剧角色列表
    try:
        char_job = (
            CharacterAnnotationJob.objects.filter(media=job.media, status=BaseJob.STATUS.COMPLETED)
            .order_by("-modified")
            .first()
        )

        if char_job and char_job.character_stats:
            roster = char_job.character_stats.get("roster", [])
            character_list = [r.get("name") for r in roster if r.get("name")]
            character_list = sorted(list(set(character_list)))
            logger.info(f"Loaded {len(character_list)} characters for inspector.")
    except Exception as e:
        logger.warning(f"Failed to load character stats: {e}")

    # 5. 返回路径
    try:
        return_url = reverse("admin:workflow_annotationproject_change", args=[job.project.id])
    except Exception:
        return_url = "/admin/"

    context = {
        "job_id": job.id,
        "project_id": job.project.id,
        "media_url": video_url,
        "waveform_url": waveform_url,
        "return_url": return_url,
        "server_data": server_data,  # [修改] 传递 Dict
        "character_list": character_list,  # [修改] 传递 List (无需 json.dumps)
    }

    return render(request, "admin/workflow/project/annotation/workbench.html", context)


@require_POST
def annotation_save_api(request, job_id):
    try:
        job = get_object_or_404(AnnotationJob, pk=job_id)
        payload = json.loads(request.body)

        AnnotationService.save_annotation(job, payload)

        return JsonResponse({"status": "success", "message": "Saved successfully"})
    except Exception as e:
        logger.error(f"Save failed for Job {job_id}: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@require_GET
def trigger_audit(request, project_id):
    project = AnnotationProject.objects.get(id=project_id)
    report = project.run_audit()
    return JsonResponse(report)


def export_project_view(request, project_id):
    project = get_object_or_404(AnnotationProject, id=project_id)

    if not project.project_export_file:
        try:
            project.export_project_annotation()
        except Exception as e:
            return HttpResponse(f"导出失败: {str(e)}", status=500)

    if project.project_export_file:
        response = HttpResponse(project.project_export_file, content_type="application/json")
        response[
            "Content-Disposition"
        ] = f'attachment; filename="{project.project_export_file.name.split("/")[-1]}"'  # noqa: E702
        return response

    return HttpResponse("导出文件未生成", status=404)


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
