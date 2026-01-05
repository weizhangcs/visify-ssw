# apps/atomflow/refinery/services/slice_regrouper.py
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from apps.workflow.common.cloud_client import CloudApiService

logger = logging.getLogger(__name__)


class SliceRegrouperService:
    """
    [Refinery Operator] 场景聚类与归纳算子 (Cloud LLM)。

    职责：
    1. 接收富切片列表。
    2. 构造 Cloud API 请求 Payload (生产模式)。
    3. 调用 Cloud SLICE_REGROUPER 接口。
    4. 等待任务完成并下载分析结果。
    """

    @staticmethod
    def run(
        client: CloudApiService,
        slices: List[Dict[str, Any]],
        lang: str,
        model_name: str,
        temp_file_path: Path,
    ) -> Dict[str, Any]:
        """
        执行场景聚类与归纳任务。

        Args:
            client: CloudApiService 实例。
            slices: 富切片列表，格式 List[MultimodalSlice.model_dump()]。
            lang: 目标语言代码 ("zh" or "en")。
            model_name: 使用的 LLM 模型名称。
            temp_file_path: 用于存储 slices 数据的临时文件路径。

        Returns:
            分析结果字典 (包含 scenes 列表)。

        Raises:
            RuntimeError: 如果任务创建、执行或下载失败。
        """
        if not slices:
            return {"scenes": []}

        # 1. 将 slices 数据写入临时文件
        try:
            with open(temp_file_path, "w", encoding="utf-8") as f:
                json.dump(slices, f, ensure_ascii=False)
        except Exception as e:
            raise RuntimeError(f"SliceRegrouper: Failed to write temp file: {e}")

        # 2. 上传文件
        success, upload_rel_path = client.upload_file(temp_file_path)
        if not success:
            raise RuntimeError(f"SliceRegrouper: Failed to upload slices file - {upload_rel_path}")

        # 3. 构造任务 Payload
        payload = {
            "lang": lang,
            "model": model_name,
            "slices_file_path": upload_rel_path,
        }

        # 4. 创建任务
        api_success, task_response = client.create_task("SLICE_REGROUPER", payload)
        if not api_success:
            raise RuntimeError(f"SliceRegrouper: Task creation failed - {task_response}")

        task_id = task_response.get("id")
        logger.info(f"SliceRegrouper: Task {task_id} created. Waiting for completion...")

        # 5. 阻塞等待任务完成
        complete_success, final_data = client.wait_for_task_completion(task_id)
        if not complete_success:
            raise RuntimeError(f"SliceRegrouper: Task failed or timed out - {final_data}")

        # 6. 获取结果
        download_url = final_data.get("download_url")
        if download_url:
            dl_success, content_bytes = client.download_task_result(download_url)
            if not dl_success:
                raise RuntimeError("SliceRegrouper: Failed to download result file")
            data = json.loads(content_bytes.decode("utf-8"))
            logger.info(f"SliceRegrouper: Downloaded result keys: {list(data.keys())}")
            return data

        # Fallback: 结果直接在 payload 中
        return final_data.get("result", {})
