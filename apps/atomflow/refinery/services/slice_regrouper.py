# apps/atomflow/refinery/services/slice_regrouper.py
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from apps.common.cloud_client import CloudApiService
from apps.common.schemas.refinery.slice_regrouper import MultimodalSlice as ExecMultimodalSlice
from apps.common.schemas.refinery.slice_regrouper import SliceRegrouperPayload, SliceRegrouperResponse

logger = logging.getLogger(__name__)


class SliceRegrouperService:
    """
    [Refinery Operator] 场景聚类与归纳算子 (Cloud LLM)。

    职责：
    1. 接收富切片列表 (Rich Slices) 并转换为 Execution Schema。
    2. 构造 Cloud API 请求 Payload。
    3. 调用 Cloud REFINERY_SLICE_REGROUPER 接口。
    4. 等待任务完成并下载分析结果。
    """

    @staticmethod
    def run(
        client: CloudApiService,
        slices: List[Dict[str, Any]],
        dialogues: List[Dict[str, Any]],
        lang: str,
    ) -> SliceRegrouperResponse:
        """
        执行场景聚类与归纳任务。

        Args:
            client: CloudApiService 实例。
            slices: 富切片列表，格式 List[MultimodalSlice.model_dump()]。
            dialogues: 对白数据 (SSOT)，用于 Hydration。
            lang: 目标语言代码 ("zh" or "en")。

        Returns:
            SliceRegrouperResponse 对象。

        Raises:
            RuntimeError: 如果任务创建、执行或下载失败。
        """
        if not slices:
            return {"scenes": []}

        # [Phase 1] Build Lookup Map
        dialogue_map = {d["id"]: d for d in dialogues if d.get("id")}

        # 1. 数据转换 (Dict -> Execution Schema)
        # 使用 Pydantic 进行转换和校验，确保符合 Cloud 契约
        exec_slices = []
        try:
            for s in slices:
                s_copy = s.copy()

                # [Phase 1] Hydrate Text Data
                d_ids = s_copy.get("dialogue_ids", [])
                text_contents = []
                for d_id in d_ids:
                    if d_id in dialogue_map:
                        text_contents.append(dialogue_map[d_id])
                s_copy["text_contents"] = text_contents

                # [Adapter] Flatten SliceTypeLabel to string for Cloud API
                # Local 'type' is {'value': '...', 'label': '...'}, Cloud expects 'value' string
                if isinstance(s_copy.get("type"), dict):
                    s_copy["type"] = s_copy["type"].get("value")

                exec_slices.append(ExecMultimodalSlice(**s_copy))
        except Exception as e:
            raise ValueError(f"SliceRegrouper: Data validation failed - {e}")

        # 2. 写入临时文件并上传
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
            # exclude_none=True 确保不发送空字段
            json.dump([s.model_dump(exclude_none=True) for s in exec_slices], tmp, ensure_ascii=False)
            temp_path = Path(tmp.name)

        try:
            success, upload_path = client.upload_file(temp_path)
            if not success:
                raise RuntimeError(f"SliceRegrouper: Failed to upload slices file - {upload_path}")
        finally:
            temp_path.unlink(missing_ok=True)

        # 3. 构造任务 Payload
        try:
            payload = SliceRegrouperPayload(lang=lang, mode="PROD", slices_file_path=upload_path)
        except ValueError as e:
            raise ValueError(f"SliceRegrouper: Payload validation failed - {e}")

        # 4. 创建任务
        api_success, task_response = client.create_task(
            "REFINERY_SLICE_REGROUPER", payload.model_dump(exclude_none=True)
        )
        if not api_success:
            raise RuntimeError(f"SliceRegrouper: Task creation failed - {task_response}")

        task_id = task_response.get("id")
        logger.info(f"SliceRegrouper: Task {task_id} created. Waiting for completion...")

        # 5. 阻塞等待任务完成
        complete_success, final_data = client.wait_for_task_completion(task_id)
        if not complete_success:
            raise RuntimeError(f"SliceRegrouper: Task failed or timed out - {final_data}")

        # 6. 获取结果
        # VSS Cloud 返回标准: 顶层 download_url 用于下载结果文件
        download_url = final_data.get("download_url")

        if download_url:
            dl_success, content_bytes = client.download_task_result(download_url)
            if not dl_success:
                raise RuntimeError(f"SliceRegrouper: Failed to download result file from {download_url}")
            try:
                # Use Pydantic validation
                return SliceRegrouperResponse.model_validate_json(content_bytes.decode("utf-8"))
            except Exception as e:
                raise RuntimeError(f"SliceRegrouper: Failed to parse result JSON: {e}")

        raise RuntimeError("SliceRegrouper: Task completed but no download_url provided.")
