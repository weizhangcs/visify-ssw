import requests
import json
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import get_object_or_404, redirect
from django.template import TemplateDoesNotExist
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from .models import Media, Asset
from .tasks import export_data_from_ls, ingest_media_files
from pathlib import Path
from django.shortcuts import render
from django.contrib import admin


# 视图一：创建 LS 项目并导入任务
# 文件路径: apps/media_assets/views.py

@login_required
def create_label_studio_project(request, media_id):
    try:
        media = Media.objects.get(pk=media_id)
    except Media.DoesNotExist:
        raise Http404("Media not found")

    # --- 准备 URL 地址 ---
    # 内部服务间通信，使用服务名，效率更高更稳定
    internal_ls_url = settings.LABEL_STUDIO_URL
    # 生成给浏览器重定向用的外部公开地址
    public_ls_url = settings.LABEL_STUDIO_PUBLIC_URL

    # 如果项目已创建，则直接跳转到公开地址
    if media.label_studio_project_id:
        redirect_url = f"{public_ls_url}/projects/{media.label_studio_project_id}"
        messages.info(request, "该媒资已在 Label Studio 中创建项目，将直接跳转。")
        return HttpResponseRedirect(redirect_url)

    # --- 1. 准备 API 调用所需的基础信息 ---
    api_token = settings.LABEL_STUDIO_ACCESS_TOKEN
    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    # --- 2. 加载自定义标注模板 ---
    try:
        # 确保模板文件名正确
        label_config_xml = render_to_string('ls_templates/video.xml')
    except TemplateDoesNotExist:
        messages.error(request, "错误：未找到 Label Studio 的标注模板文件。")
        return redirect('admin:media_assets_media_change', object_id=media.id)

    # --- 3. 动态生成回调 URL 和 expert_instruction ---
    return_to_django_url = request.build_absolute_uri(
        reverse('admin:media_assets_media_change', args=[media.id])
    )
    expert_instruction_html = f"""
    <h4>操作指南</h4>
    <p>请为《{media.title}》下的所有剧集（Tasks）完成标注。</p>
    <hr style="margin: 20px 0;">
    <a href="{return_to_django_url}" target="_blank" style="...">↩️ 返回 Django 媒资主页</a>
    """

    # --- 4. 调用 API 创建 Project ---
    project_payload = {
        "title": f"{media.title} - 标注项目",
        "expert_instruction": expert_instruction_html,
        "label_config": label_config_xml,
    }

    try:
        # 使用内部地址进行 API 调用
        project_response = requests.post(f"{internal_ls_url}/api/projects", json=project_payload, headers=headers)
        project_response.raise_for_status()
        project_data = project_response.json()
        project_id = project_data.get("id")

        if not project_id:
            messages.error(request, "API 调用成功，但未返回项目ID。")
            return redirect('admin:media_assets_media_changelist')

        media.label_studio_project_id = project_id
        media.save()

        # --- 5. 循环导入 Tasks ---
        assets_to_label = media.assets.all()
        for asset in assets_to_label:
            if not asset.processed_video_url:
                messages.warning(request, f"剧集 '{asset.title}' 没有处理后的视频URL，跳过导入。")
                continue

            task_payload = {"data": {"video_url": asset.processed_video_url}}

            # 同样，使用内部地址进行 API 调用
            task_response = requests.post(f"{internal_ls_url}/api/projects/{project_id}/tasks", json=task_payload,
                                          headers=headers)

            if task_response.status_code == 201:
                task_id = task_response.json().get('id')
                asset.label_studio_task_id = task_id
                asset.l2_l3_status = 'in_progress'
                asset.save()
            else:
                messages.error(request, f"为剧集 '{asset.title}' 创建 Task 失败: {task_response.text}")

        messages.success(request, f"成功在 Label Studio 中创建项目 (ID: {project_id}) 并导入任务！")
        # 最终重定向到给浏览器访问的公开地址
        return HttpResponseRedirect(f"{public_ls_url}/projects/{project_id}")

    except requests.exceptions.RequestException as e:
        messages.error(request, f"调用 Label Studio API 失败: {e}")
        return redirect('admin:media_assets_media_changelist')

@login_required
def mark_asset_as_complete(request, asset_id):
    asset = get_object_or_404(Asset, pk=asset_id)

    # 1. 更新状态
    asset.l2_l3_status = 'completed'
    asset.save(update_fields=['l2_l3_status'])

    # 2. 触发后台任务去拉取数据
    print(f"触发异步任务，从 LS 导出 Asset: {asset.id} 的标注数据。")
    export_data_from_ls.delay(str(asset.id))

    # 3. 添加成功消息并重定向回 Admin 页面
    messages.success(request, f"已为《{asset.title}》发送“完成”信号！结果将在后台自动同步。")
    return redirect('admin:apps_media_assets_asset_change', object_id=asset.id)

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