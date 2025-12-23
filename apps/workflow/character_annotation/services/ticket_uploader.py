import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

import requests

# [Critical] 引入 Edge 配置模型
from apps.configuration.models import IntegrationSettings

logger = logging.getLogger(__name__)

# 配置常量
BATCH_SIZE = 500
MAX_RETRIES = 3
UPLOAD_TIMEOUT = 30


class VSSCloudService:
    """
    [Infrastructure] VSS Cloud 通讯服务
    职责：自动从数据库加载配置，并封装 HTTP 请求
    """

    def __init__(self):
        # 1. 从 IntegrationSettings 模型安全地加载配置
        try:
            settings = IntegrationSettings.get_solo()
        except Exception as e:
            logger.warning(f"IntegrationSettings load failed: {e}")
            settings = None

        # 使用 getattr 安全获取值，并提供硬编码的回退值 (仅用于开发环境本地回退)
        self.BASE_URL = getattr(settings, "cloud_api_base_url", None) or "http://localhost:8080"
        self.INSTANCE_ID = getattr(settings, "cloud_instance_id", None)
        self.API_KEY = getattr(settings, "cloud_api_key", None)

        # 移除末尾斜杠以规范化
        if self.BASE_URL:
            self.BASE_URL = self.BASE_URL.rstrip("/")

        # 2. 验证检查
        if not self.INSTANCE_ID or not self.API_KEY:
            logger.error("❌ CloudApiService 凭证不完整！请检查 IntegrationSettings 表。")
            # 这里不抛出异常，允许在无网络环境下初始化，但在调用时会失败

        self.session = requests.Session()
        # 设置默认 Headers
        self.headers = {
            "X-Api-Key": self.API_KEY if self.API_KEY else "",
            # 部分鉴权中间件可能需要显式 Instance ID
            "X-Instance-ID": str(self.INSTANCE_ID) if self.INSTANCE_ID else "",
        }

    def post(self, endpoint: str, json_data: Dict) -> Dict:
        """发送 JSON POST 请求"""
        self._check_config()
        url = f"{self.BASE_URL}{endpoint}"
        try:
            resp = self.session.post(url, json=json_data, headers=self.headers, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Cloud API POST failed ({url}): {e}")
            raise

    def post_file(self, endpoint: str, files: Dict) -> Dict:
        """发送 multipart/form-data 请求 (用于上传 JSON)"""
        self._check_config()
        url = f"{self.BASE_URL}{endpoint}"
        try:
            # 注意: files 请求不应手动设置 Content-Type，requests 会自动处理 boundary
            resp = self.session.post(url, files=files, headers=self.headers, timeout=120)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Cloud API File Upload failed ({url}): {e}")
            raise

    def _check_config(self):
        if not self.API_KEY or not self.BASE_URL:
            raise RuntimeError("Cloud Service misconfigured. Missing API_KEY or BASE_URL in IntegrationSettings.")


class TicketUploader:
    """
    [Edge Transport] 分批次、带重试的 GCS 直传器
    """

    def __init__(self, asset_id: str, media_id: str = None):
        # 自动初始化 Cloud Service，不再依赖外部注入
        self.client = VSSCloudService()
        self.asset_id = asset_id
        self.media_id = media_id

        # 用于 GCS 直传的 Session (不带 Cloud API Key，避免污染)
        self.gcs_session = requests.Session()

    def upload_files(self, local_files: List[Path]) -> Dict[str, str]:
        if not local_files:
            return {}

        total_files = len(local_files)
        logger.info(f"[Uploader] Starting batch upload for {total_files} files (Asset: {self.asset_id})...")

        final_mapping = {}
        chunks = [local_files[i : i + BATCH_SIZE] for i in range(0, total_files, BATCH_SIZE)]

        for idx, chunk in enumerate(chunks):
            logger.info(f"[Uploader] Processing Batch {idx + 1}/{len(chunks)}...")
            try:
                mapping = self._process_batch(chunk)
                final_mapping.update(mapping)
            except Exception as e:
                logger.error(f"[Uploader] Batch {idx + 1} failed: {e}")
                raise RuntimeError(f"Critical upload failure in batch {idx + 1}: {e}")

        logger.info(f"[Uploader] Upload complete. {len(final_mapping)}/{total_files} files success.")
        return final_mapping

    def _process_batch(self, files: List[Path]) -> Dict[str, str]:
        filename_map = {f.name: f for f in files}
        filenames = list(filename_map.keys())

        # A. 换票 (使用 VSSCloudService)
        payload = {"asset_id": self.asset_id, "media_id": self.media_id, "filenames": filenames}

        # 调用 Cloud 接口
        resp = self.client.post("/api/v1/files/upload-ticket", payload)

        base_path = resp["upload_base_path"]
        signed_urls = resp["signed_urls"]

        # B. 并发上传
        batch_mapping = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_file = {
                executor.submit(self._put_file_with_retry, filename_map[fname], url): fname
                for fname, url in signed_urls.items()
            }

            for future in as_completed(future_to_file):
                fname = future_to_file[future]
                local_path = filename_map[fname]
                future.result()  # 异常会在主循环捕获

                # 构造 GS 路径
                gs_uri = f"{base_path}{fname}"
                batch_mapping[str(local_path)] = gs_uri

        return batch_mapping

    def _put_file_with_retry(self, local_path: Path, signed_url: str):
        file_size = local_path.stat().st_size
        for attempt in range(MAX_RETRIES):
            try:
                with open(local_path, "rb") as f:
                    headers = {"Content-Type": "application/octet-stream", "Content-Length": str(file_size)}
                    # 使用 gcs_session (纯净 Session)
                    resp = self.gcs_session.put(signed_url, data=f, headers=headers, timeout=UPLOAD_TIMEOUT)
                    resp.raise_for_status()
                    return
            except requests.exceptions.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 * (attempt + 1))
                else:
                    raise RuntimeError(f"Max retries exceeded for {local_path.name}: {e}")
