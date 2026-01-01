# apps/atomflow/refinery/services/uploader.py
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

import requests

logger = logging.getLogger(__name__)


class TicketUploader:
    """[Edge Transport] 纯粹的搬运算子"""

    BATCH_SIZE = 500

    def __init__(self, material_id: str, asset_id: str, cloud_client):
        self.client = cloud_client
        self.material_id = material_id  # 实际的 material_id
        self.asset_id = asset_id
        self.gcs_session = requests.Session()

    def upload_files(self, local_files: List[Path]) -> Dict[str, str]:
        if not local_files:
            logger.info(f"[{self.material_id}] No files to upload, skipping.")
            return {}

        total_count = len(local_files)
        logger.info(f"[{self.material_id}] Starting sync: {total_count} files identified.")

        final_mapping = {}
        chunks = [local_files[i : i + self.BATCH_SIZE] for i in range(0, total_count, self.BATCH_SIZE)]
        total_batches = len(chunks)

        for idx, chunk in enumerate(chunks, 1):
            # --- 过程日志：批次开始 ---
            logger.info(f"[{self.material_id}] Progress: Batch {idx}/{total_batches} start ({len(chunk)} files).")

            try:
                mapping = self._process_batch(chunk, batch_index=idx)
                final_mapping.update(mapping)
                # --- 过程日志：批次成功 ---
                logger.info(f"[{self.material_id}] Progress: Batch {idx}/{total_batches} upload successful.")
            except Exception as e:
                # 记录具体哪一个 Batch 挂了
                logger.error(f"[{self.material_id}] Critical failure in Batch {idx}: {str(e)}")
                raise

        logger.info(f"[{self.material_id}] All sync tasks completed. {len(final_mapping)} files in cloud.")
        return final_mapping

    def _process_batch(self, files: List[Path], batch_index: int) -> Dict[str, str]:
        filename_map = {f.name: f for f in files}

        # 1. 换票阶段日志
        logger.info(f"[{self.material_id}] Batch {batch_index}: Requesting {len(files)} tickets from cloud...")

        start_ticket = time.time()
        # [Fix] 使用 CloudApiService 统一封装的方法，避免手动拼接 URL
        resp = self.client.get_upload_tickets(
            asset_id=self.asset_id, media_id=self.material_id, filenames=list(filename_map.keys())
        )

        base_path = resp["upload_base_path"]
        signed_urls = resp["signed_urls"]
        logger.info(
            f"[{self.material_id}] Batch {batch_index}: Tickets received ({time.time() - start_ticket:.2f}s)."  # noqa : E231
        )

        # 2. 并发上传阶段日志
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
        with open(local_path, "rb") as f:
            resp = self.gcs_session.put(
                signed_url, data=f, headers={"Content-Type": "application/octet-stream"}, timeout=30
            )
            resp.raise_for_status()
