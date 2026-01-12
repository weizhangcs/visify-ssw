# apps/atomflow/refinery/services/slice_regrouper.py
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from apps.atomflow.refinery.schemas import SceneType
from apps.common.cloud_client import CloudApiService
from apps.common.schemas.refinery.slice_regrouper import MultimodalSlice as ExecMultimodalSlice
from apps.common.schemas.refinery.slice_regrouper import SliceRegrouperPayload

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
        lang: str,
    ) -> Dict[str, Any]:
        """
        执行场景聚类与归纳任务。

        Args:
            client: CloudApiService 实例。
            slices: 富切片列表，格式 List[MultimodalSlice.model_dump()]。
            lang: 目标语言代码 ("zh" or "en")。

        Returns:
            分析结果字典 (包含 scenes 列表)。

        Raises:
            RuntimeError: 如果任务创建、执行或下载失败。
        """
        if not slices:
            return {"scenes": []}

        # 1. 数据转换 (Dict -> Execution Schema)
        # 使用 Pydantic 进行转换和校验，确保符合 Cloud 契约
        exec_slices = []
        try:
            for s in slices:
                # [Adapter] Flatten SliceTypeLabel to string for Cloud API
                # Local 'type' is {'value': '...', 'label': '...'}, Cloud expects 'value' string
                s_copy = s.copy()
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
                data = json.loads(content_bytes.decode("utf-8"))

                # [Adapter] Hydrate SceneType string to SceneTypeLabel
                scenes = data.get("scenes", [])
                for scene in scenes:
                    content = scene.get("content", {})
                    if "scene_type" in content:
                        raw_type = content["scene_type"]
                        if isinstance(raw_type, str):
                            content["scene_type"] = SliceRegrouperService._get_scene_type_label(raw_type, lang)
                return data
            except Exception as e:
                raise RuntimeError(f"SliceRegrouper: Failed to parse result JSON: {e}")

        raise RuntimeError("SliceRegrouper: Task completed but no download_url provided.")

    @staticmethod
    def _get_scene_type_label(value: str, lang: str = "zh") -> Dict[str, str]:
        """Helper to construct SceneTypeLabel with i18n."""
        labels = {
            SceneType.DIALOGUE: {"zh": "对话/文戏", "en": "Dialogue"},
            SceneType.ACTION: {"zh": "动作/冲突", "en": "Action"},
            SceneType.MONTAGE: {"zh": "蒙太奇", "en": "Montage"},
            SceneType.ESTABLISHING: {"zh": "建立/空镜", "en": "Establishing"},
            SceneType.EMOTIONAL: {"zh": "情感/特写", "en": "Emotional"},
        }
        label_text = labels.get(value, {}).get(lang, "Unknown")
        return {"value": value, "label": label_text}
