# apps/atomflow/refinery/services/uploader.py
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)


class TicketUploader:
    """
    [Edge Transport] 文件批量上传服务。

    职责：
    1. 向 VSS Cloud 批量申请上传凭证 (Signed URLs)。
    2. 使用线程池并发上传本地文件。
    3. 返回本地路径到云端路径的映射。
    """

    BATCH_SIZE = 500

    def __init__(self, material_id: str, asset_id: str, cloud_client):
        """
        初始化 Uploader。

        Args:
            material_id: 物料 ID。
            asset_id: 资产 ID。
            cloud_client: 已配置的 CloudApiService 实例。
        """
        self.client = cloud_client
        self.material_id = material_id  # 实际的 material_id
        self.asset_id = asset_id
        self.gcs_session = requests.Session()

        # [Fix] 优化连接池配置，增加底层连接重试 (针对握手/Header阶段)
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=3)
        self.gcs_session.mount("https://", adapter)

    def upload_files(self, local_files: List[Path]) -> Dict[str, str]:
        """
        执行批量上传。

        Args:
            local_files: 本地文件路径列表 (Path 对象)。

        Returns:
            一个字典，映射关系为：str(本地绝对路径) -> 云端 URL。
        """
        if not local_files:
            logger.info(f"[{self.material_id}] No files to upload, skipping.")
            return {}

        total_count = len(local_files)
        logger.info(f"[{self.material_id}] Starting sync: {total_count} files identified.")

        final_mapping = {}
        chunks = [local_files[i : i + self.BATCH_SIZE] for i in range(0, total_count, self.BATCH_SIZE)]
        total_batches = len(chunks)

        for idx, chunk in enumerate(chunks, 1):
            logger.info(f"[{self.material_id}] Progress: Batch {idx}/{total_batches} start ({len(chunk)} files).")

            try:
                mapping = self._process_batch(chunk, batch_index=idx)
                final_mapping.update(mapping)
                logger.info(f"[{self.material_id}] Progress: Batch {idx}/{total_batches} upload successful.")
            except Exception as e:
                logger.error(f"[{self.material_id}] Critical failure in Batch {idx}: {str(e)}")
                raise

        logger.info(f"[{self.material_id}] All sync tasks completed. {len(final_mapping)} files in cloud.")
        return final_mapping

    def _process_batch(self, files: List[Path], batch_index: int) -> Dict[str, str]:
        """
        [内部方法] 处理单个批次的文件上传。
        """
        filename_map = {f.name: f for f in files}

        # 1. 换票阶段
        logger.info(f"[{self.material_id}] Batch {batch_index}: Requesting {len(files)} tickets from cloud...")

        start_ticket = time.time()
        # [Fix] 使用 CloudApiService 统一封装的方法，避免手动拼接 URL
        resp = self.client.get_upload_tickets(
            asset_id=self.asset_id, media_id=self.material_id, filenames=list(filename_map.keys())
        )

        base_path = resp["upload_base_path"]
        signed_urls = resp["signed_urls"]
        logger.info(
            f"[{self.material_id}] Batch {batch_index}: Tickets received ({time.time() - start_ticket:.2f}s)."  # noqa: E231, E501
        )

        # 2. 并发上传阶段
        batch_mapping = {}
        completed = 0
        total_in_batch = len(signed_urls)

        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_path = {
                executor.submit(self._put_file, filename_map[fname], url): filename_map[fname]
                for fname, url in signed_urls.items()
            }

            for future in as_completed(future_to_path):
                local_path = future_to_path[future]
                future.result()
                batch_mapping[str(local_path)] = f"{base_path}{local_path.name}"

                completed += 1
                # 每完成 100 个文件打一次微进度，防止大 Batch 内部黑盒
                if completed % 100 == 0:
                    logger.info(
                        f"[{self.material_id}] Batch {batch_index}: Sub-progress {completed}/{total_in_batch}..."
                    )

        return batch_mapping

    def _put_file(self, local_path: Path, signed_url: str):
        """
        [内部方法] 上传单个文件到 GCS/S3。
        """
        # [Fix] 增加应用层重试机制，处理 RemoteDisconnected 等网络不稳定情况
        # 对于文件流上传，requests 无法自动重试 (因为无法 rewind file)，需手动处理
        max_retries = 3
        timeout = 60  # [Fix] 增加超时时间 (原 30s)
        last_exception = None

        with open(local_path, "rb") as f:
            for attempt in range(max_retries):
                try:
                    f.seek(0)  # 每次重试前重置文件指针

                    resp = self.gcs_session.put(
                        signed_url, data=f, headers={"Content-Type": "application/octet-stream"}, timeout=timeout
                    )
                    resp.raise_for_status()
                    return  # 成功则直接返回
                except requests.RequestException as e:
                    last_exception = e
                    logger.warning(
                        f"[{self.material_id}] Upload failed for {local_path.name} (Attempt {attempt + 1}/{max_retries}): {e}"  # noqa: E501
                    )
                    # 指数退避: 1s, 2s, 4s
                    time.sleep(1 * (2**attempt))

        # 重试耗尽，抛出最后一次异常
        if last_exception:
            raise last_exception
