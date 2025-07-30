# 文件路径: apps/media_assets/services/label_studio.py

import requests
from typing import Tuple, Optional

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.template import TemplateDoesNotExist
from django.http import HttpRequest

from apps.media_assets.models import Media

class LabelStudioService:
    """
    一个封装了与 Label Studio API 交互逻辑的服务。
    """
    def __init__(self):
        self.internal_ls_url = settings.LABEL_STUDIO_URL
        self.api_token = settings.LABEL_STUDIO_ACCESS_TOKEN
        self.headers = {
            "Authorization": f"Token {self.api_token}",
            "Content-Type": "application/json",
        }

    def create_project_and_import_tasks(self, media: Media, request: HttpRequest) -> Tuple[bool, str, Optional[str]]:
        """
        创建 Label Studio 项目并导入所有关联的 Asset 作为任务。

        :param media: 要处理的 Media 对象
        :param request: Django 的 HttpRequest 对象，用于构建绝对 URL
        :return: 一个元组 (success, message, redirect_url)
        """
        try:
            # 1. 加载自定义标注模板
            label_config_xml = render_to_string('ls_templates/video.xml')

            # 2. 动态生成回调 URL 和 expert_instruction
            return_to_django_url = request.build_absolute_uri(
                reverse('admin:media_assets_media_change', args=[media.id])
            )
            expert_instruction_html = f"""
            <h4>操作指南</h4>
            <p>请为《{media.title}》下的所有剧集（Tasks）完成标注。</p>
            <hr style="margin: 20px 0;">
            <a href="{return_to_django_url}" target="_blank" style="...">↩️ 返回 Django 媒资主页</a>
            """

            # 3. 调用 API 创建 Project
            project_payload = {
                "title": f"{media.title} - 标注项目",
                "expert_instruction": expert_instruction_html,
                "label_config": label_config_xml,
            }
            project_response = requests.post(f"{self.internal_ls_url}/api/projects", json=project_payload, headers=self.headers)
            project_response.raise_for_status()
            project_data = project_response.json()
            project_id = project_data.get("id")

            if not project_id:
                return False, "API 调用成功，但未返回项目ID。", None

            media.label_studio_project_id = project_id
            media.save(update_fields=['label_studio_project_id'])

            # 4. 循环导入 Tasks
            assets_to_label = media.assets.all()
            for asset in assets_to_label:
                if not asset.processed_video_url:
                    print(f"警告: 剧集 '{asset.title}' 没有处理后的视频URL，跳过导入。")
                    continue

                task_payload = {"data": {"video_url": asset.processed_video_url}}
                task_response = requests.post(f"{self.internal_ls_url}/api/projects/{project_id}/tasks", json=task_payload,
                                              headers=self.headers)

                if task_response.status_code == 201:
                    task_id = task_response.json().get('id')
                    asset.label_studio_task_id = task_id
                    asset.l2_l3_status = 'in_progress'
                    asset.save(update_fields=['label_studio_task_id', 'l2_l3_status'])
                else:
                    # 即使单个任务失败，也继续尝试导入其他任务
                    print(f"为剧集 '{asset.title}' 创建 Task 失败: {task_response.text}")

            message = f"成功在 Label Studio 中创建项目 (ID: {project_id}) 并导入任务！"
            redirect_url = media.get_label_studio_project_url()
            return True, message, redirect_url

        except TemplateDoesNotExist:
            return False, "错误：未找到 Label Studio 的标注模板文件。", None
        except requests.exceptions.RequestException as e:
            return False, f"调用 Label Studio API 失败: {e}", None
        except Exception as e:
            return False, f"创建 LS 项目时发生未知错误: {e}", None