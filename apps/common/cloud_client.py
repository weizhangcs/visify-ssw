# 文件路径: apps/common/cloud_client.py
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests

from apps.configuration.models import IntegrationSettings

logger = logging.getLogger(__name__)


class CloudApiService:
    """
    一个封装了与 Visify Story Studio Cloud API 交互逻辑的服务。
    已适配 Django Ninja 框架 (移除末尾斜杠)。
    """

    def __init__(self):
        try:
            settings = IntegrationSettings.get_solo()
        except Exception:
            settings = None

        self.BASE_URL = getattr(settings, "cloud_api_base_url", None) or "http://localhost:8080"
        self.INSTANCE_ID = getattr(settings, "cloud_instance_id", None)
        self.API_KEY = getattr(settings, "cloud_api_key", None)

        if not self.BASE_URL or not self.INSTANCE_ID or not self.API_KEY:
            logger.warning("CloudApiService 凭证不完整。请检查 IntegrationSettings。")

    def _get_auth_headers(self) -> Dict[str, str]:
        return {
            "X-Instance-ID": self.INSTANCE_ID,
            "X-Api-Key": self.API_KEY,
        }

    def upload_file(self, local_file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        执行 [第1步：上传]
        [注意] 适配 Ninja: 移除 /api/v1/files/upload/ 末尾的斜杠
        """
        if not local_file_path.exists():
            logger.error(f"Cloud API: 无法上传，文件未找到: {local_file_path}")
            return False, "File not found"

        # 核心修正：移除末尾斜杠
        upload_url = f"{self.BASE_URL.rstrip('/')}/api/v1/files/upload"
        headers = self._get_auth_headers()

        try:
            with open(local_file_path, "rb") as f:
                files = {"file": (local_file_path.name, f)}
                response = requests.post(upload_url, headers=headers, files=files, timeout=300)

            response.raise_for_status()
            response_data = response.json()
            relative_path = response_data.get("relative_path")

            if relative_path:
                logger.info(f"Cloud API: 文件上传成功: {relative_path}")
                return True, relative_path
            else:
                return False, "Upload succeeded but response format is invalid."

        except requests.exceptions.RequestException as e:
            logger.error(f"Cloud API: 文件上传失败: {e}", exc_info=True)
            return False, str(e)

    def create_task(self, task_type: str, payload: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        执行 [第2步：创建]
        [注意] 适配 Ninja: 移除 /api/v1/tasks/ 末尾的斜杠
        """
        # 核心修正：移除末尾斜杠
        create_url = f"{self.BASE_URL.rstrip('/')}/api/v1/tasks/"
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"

        full_payload = {"task_type": task_type, "payload": payload}

        try:
            response = requests.post(create_url, headers=headers, json=full_payload, timeout=60)
            response.raise_for_status()

            response_data = response.json()
            task_id = response_data.get("id")

            if task_id:
                logger.info(f"Cloud API: 成功创建任务 '{task_type}' (Task ID: {task_id})。")
                return True, response_data
            else:
                return False, "Create task succeeded but response format is invalid."

        except requests.exceptions.RequestException as e:
            logger.error(f"Cloud API: 创建任务失败: {e}", exc_info=True)
            return False, {"message": str(e)}

    def get_task_status(self, task_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        执行 [第3步：轮询]
        [注意] 适配 Ninja: 移除 /api/v1/tasks/{task_id}/ 末尾的斜杠
        """
        # 核心修正：移除末尾斜杠
        status_url = f"{self.BASE_URL.rstrip('/')}/api/v1/tasks/{task_id}"
        headers = self._get_auth_headers()

        try:
            response = requests.get(status_url, headers=headers, timeout=60)
            response.raise_for_status()

            response_data = response.json()
            if "status" in response_data:
                return True, response_data
            else:
                return False, None

        except requests.exceptions.RequestException as e:
            logger.error(f"Cloud API: 查询任务 {task_id} 失败: {e}", exc_info=True)
            return False, None

    def download_task_result(self, download_url: str) -> Tuple[bool, Optional[bytes]]:
        """
        执行 [第4步：下载] (此处的 URL 由 Cloud 返回，通常已处理好)
        """
        if not download_url.startswith("http"):
            logger.error(f"Cloud API: 无效的 download_url: {download_url}")
            return False, None

        if "/api/v1/" in download_url:
            try:
                parsed_url = urlparse(download_url)
                if parsed_url.path.startswith("/api/v1/"):
                    base = self.BASE_URL.rstrip("/")
                    path = parsed_url.path.lstrip("/")
                    new_url = f"{base}/{path}"
                    if parsed_url.query:
                        new_url += f"?{parsed_url.query}"
                    download_url = new_url
            except Exception as e:
                logger.warning(f"Cloud API: URL 修正失败: {e}")

        headers = self._get_auth_headers()
        try:
            response = requests.get(download_url, headers=headers, timeout=300)
            response.raise_for_status()
            return True, response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"Cloud API: 下载结果失败: {e}", exc_info=True)
            return False, None

    def download_general_file(self, file_path: str) -> Tuple[bool, Optional[bytes]]:
        """
        调用“通用资产下载接口”
        [注意] 适配 Ninja: 移除 /api/v1/files/download/ 末尾的斜杠
        """
        # 核心修正：移除末尾斜杠
        download_url = f"{self.BASE_URL.rstrip('/')}/api/v1/files/download"
        headers = self._get_auth_headers()
        params = {"path": file_path}

        try:
            response = requests.get(download_url, headers=headers, params=params, timeout=300)
            response.raise_for_status()
            return True, response.content
        except requests.exceptions.RequestException as e:
            logger.error(f"Cloud API: 下载通用文件失败: {file_path}。错误: {e}", exc_info=True)
            return False, None

    def get_upload_tickets(self, asset_id: str, media_id: str, filenames: list) -> Dict[str, Any]:
        """
        [同步接口] 向云端换取 GCS/S3 预签名上传地址 (Tickets)
        用于大规模帧数据的直传。
        """
        endpoint = f"{self.BASE_URL.rstrip('/')}/api/v1/files/upload-ticket"
        headers = self._get_auth_headers()
        payload = {"asset_id": asset_id, "media_id": media_id, "filenames": filenames}

        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Cloud API: 换票请求失败: {e}", exc_info=True)
            raise RuntimeError(f"Failed to fetch upload tickets: {str(e)}")

    def wait_for_task_completion(
        self, task_id: int, timeout: int = 1800, interval: int = 10
    ) -> Tuple[bool, Optional[Dict]]:
        """
        [同步阻塞轮询]
        让调用者像调用同步 API 一样等待异步任务完成。
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            success, data = self.get_task_status(task_id)
            if not success:
                return False, {"message": "Query failed"}

            status = data.get("status")
            if status == "COMPLETED":
                return True, data
            if status == "FAILED":
                return False, data

            time.sleep(interval)

        return False, {"message": "Task timeout"}
