# 文件路径: apps/media_assets/views.py
import requests
import json
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, redirect

from django.contrib.auth.decorators import login_required

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from .models import Media, Asset
from .tasks import export_data_from_ls, ingest_media_files, generate_narrative_blueprint, process_single_asset_files
from .tasks import generate_character_report, validate_blueprint
from .services.label_studio import LabelStudioService
from pathlib import Path
from django.shortcuts import render
from django.contrib import admin

# 视图一：创建 LS 项目并导入任务
# 文件路径: apps/media_assets/views.py

@login_required
def create_label_studio_project(request, media_id):
    media = get_object_or_404(Media, pk=media_id)

    # 如果项目已存在，直接跳转
    redirect_url = media.get_label_studio_project_url()
    if redirect_url:
        messages.info(request, "该媒资已在 Label Studio 中创建项目，将直接跳转。")
        return HttpResponseRedirect(redirect_url)

    # 实例化并调用服务
    service = LabelStudioService()
    success, message, redirect_url = service.create_project_and_import_tasks(media=media, request=request)

    # 根据服务返回的结果处理响应
    if success:
        messages.success(request, message)
        return HttpResponseRedirect(redirect_url)
    else:
        messages.error(request, message)
        return redirect('admin:media_assets_media_changelist')

@login_required
def mark_media_l2l3_as_complete(request, media_id):
    """
    (正确实现) 接收来自Label Studio的“L2/L3标注完成”信号，并触发数据导出任务。
    """
    media = get_object_or_404(Media, pk=media_id)

    export_data_from_ls.delay(str(media.id))

    messages.success(request, f"已为《{media.title}》发送“L2/L3标注完成”信号！结果将在后台自动同步。")
    return redirect('admin:media_assets_media_change', object_id=media.id)

@csrf_exempt  # 来自外部 JS 的 API 请求，需要禁用 CSRF 保护
def save_l1_output(request, asset_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

    try:
        asset = Asset.objects.get(pk=asset_id)

        # 从请求体中获取 .ass 文件内容
        ass_content = request.body.decode('utf-8')

        if not ass_content:
            return JsonResponse({'status': 'error', 'message': 'No content received'}, status=400)

        # 构建文件名并保存到 l1_output_file 字段
        file_name = f"{asset.id}_l1.ass"
        asset.l1_output_file.save(file_name, ContentFile(ass_content.encode('utf-8')), save=False)

        # 更新状态
        asset.l1_status = 'completed'

        # 一次性保存所有更改
        asset.save(update_fields=['l1_output_file', 'l1_status'])

        return JsonResponse({'status': 'success', 'message': 'L1 output saved successfully.'})

    except Asset.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Asset not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def batch_file_upload_view(request, media_id):
    if request.method == 'POST':
        try:
            media = Media.objects.get(id=media_id)
            # 为这个 Media 对象创建一个专属的“接收”目录
            upload_dir = Path(settings.MEDIA_ROOT) / 'batch_uploads' / str(media.id)
            upload_dir.mkdir(parents=True, exist_ok=True)

            # request.FILES 包含了所有上传的文件
            uploaded_file = request.FILES.get('file')
            if not uploaded_file:
                return JsonResponse({'status': 'error', 'message': 'No file provided'}, status=400)

            # 将文件保存到我们的接收目录中
            file_path = upload_dir / uploaded_file.name
            with open(file_path, 'wb+') as fp:
                for chunk in uploaded_file.chunks():
                    fp.write(chunk)

            print(f"接收到文件: {uploaded_file.name}，已保存到: {file_path}")
            return JsonResponse({'status': 'success', 'message': f'File {uploaded_file.name} uploaded successfully'})

        except Media.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Media not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)

# 这个视图负责渲染我们的自定义上传页面
@login_required
def batch_upload_page_view(request, media_id):
    try:
        media = Media.objects.get(id=media_id)
        context = {
            'media': media,
            # Django Admin 需要的一些上下文变量
            'opts': Media._meta,
            'site_header': admin.site.site_header,
            'site_title': admin.site.site_title,
            'has_permission': True,
        }
        return render(request, 'admin/media_assets/media/batch_upload.html', context)
    except Media.DoesNotExist:
        raise Http404("Media not found")

@login_required
def trigger_ingest_task(request, media_id):
    """
    这个视图专门用于从前端接收信号，以启动批处理任务。
    """
    media = get_object_or_404(Media, pk=media_id)

    # 触发核心的 Celery 任务
    ingest_media_files.delay(str(media.id))

    # 向用户显示成功消息
    messages.success(request, f"已成功为《{media.title}》启动后台批量加载任务，请稍后刷新查看状态。")

    # 将用户重定向回 Media 的编辑页面
    return redirect('admin:media_assets_media_change', object_id=media.id)

@login_required
def start_l1_annotation(request, asset_id):
    """
    一个视图，用于在跳转到 SubEditor 前，将 L1 状态更新为 'in_progress'。
    """
    asset = get_object_or_404(Asset, pk=asset_id)
    if asset.l1_status == 'pending':
        asset.l1_status = 'in_progress'
        asset.save(update_fields=['l1_status'])

    target_url = asset.get_subeditor_url()
    if target_url:
        return HttpResponseRedirect(target_url)
    else:
        messages.error(request, "无法生成 SubEditor 链接，缺少必要文件。")
        return redirect('admin:media_assets_asset_changelist')

@login_required
def start_l2_l3_annotation(request, asset_id):
    """
    一个视图，用于在跳转到 Label Studio 前，将 L2/L3 状态更新为 'in_progress'。
    """
    asset = get_object_or_404(Asset, pk=asset_id)
    if asset.l2_l3_status == 'pending':
        asset.l2_l3_status = 'in_progress'
        asset.save(update_fields=['l2_l3_status'])

    target_url = asset.get_label_studio_task_url()
    if target_url:
        return HttpResponseRedirect(target_url)
    else:
        messages.error(request, "无法生成 Label Studio 任务链接。")
        return redirect('admin:media_assets_asset_changelist')

@login_required
def generate_blueprint(request, media_id):
    """
    一个专门用于触发“生成叙事蓝图”后台任务的视图。
    """
    media = get_object_or_404(Media, pk=media_id)
    generate_narrative_blueprint.delay(str(media.id))
    messages.success(request, f"已为《{media.title}》触发了“生成叙事蓝图”的后台任务。")

    # 将用户重定向回 Media 的编辑页面
    return redirect('admin:media_assets_media_change', object_id=media.id)

@login_required
def trigger_single_asset_processing(request, asset_id):
    asset = get_object_or_404(Asset, pk=asset_id)
    process_single_asset_files.delay(str(asset.id))
    messages.success(request, f"已为《{asset.title}》启动了手动文件处理任务。")
    return redirect('admin:media_assets_asset_changelist')

@login_required
def generate_character_report_view(request, media_id):
    """
    一个专门用于触发“生成角色名清单”后台任务的视图。
    """
    media = get_object_or_404(Media, pk=media_id)
    generate_character_report.delay(str(media.id))
    messages.success(request, f"已为《{media.title}》启动了“生成角色名清单”的后台任务。")
    return redirect('admin:media_assets_media_change', object_id=media.id)

@login_required
def validate_blueprint_view(request, media_id):
    """
    一个专门用于触发“验证叙事蓝图”后台任务的视图。
    """
    media = get_object_or_404(Media, pk=media_id)
    validate_blueprint.delay(str(media.id))
    messages.success(request, f"已为《{media.title}》启动了“验证叙事蓝图”的后台任务。")
    return redirect('admin:media_assets_media_change', object_id=media.id)