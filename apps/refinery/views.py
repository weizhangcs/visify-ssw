# apps/refinery/views.py

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .models import Material
from .services.scheduler import RefineryScheduler


@staff_member_required
def material_pipeline_state_api(request, material_id):
    """[API] 供 Admin 详情页或异步 JS 调用，获取当前的白盒指标"""
    material = get_object_or_404(Material, id=material_id)
    state_data = RefineryScheduler.get_pipeline_state(material)
    return JsonResponse(
        {"status": "success", "material_id": str(material_id), "fsm_status": material.status, "pipeline": state_data}
    )


@require_POST
@staff_member_required
def manual_retry_step_view(request, material_id):
    """[Action] 定点重试：从用户点击的 slug 开始恢复管线"""
    slug = request.POST.get("slug")
    if not slug:
        return JsonResponse({"status": "error", "message": "Missing step slug"}, status=400)

    try:
        # 调用 Scheduler 的手动触发逻辑，后续会自动编排
        RefineryScheduler.schedule(str(material_id), start_from_slug=slug)
        return JsonResponse({"status": "success", "message": f"Step {slug} triggered"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
