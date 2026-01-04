# 文件路径: apps/atomflow/refinery/services/character_refiner.py
import json
import logging
from pathlib import Path
from typing import Any, Dict

from apps.workflow.common.cloud_client import CloudApiService

logger = logging.getLogger(__name__)


class CharacterRefinerService:
    """
    [Refinery Operator] 角色识别算子 (Cloud LLM)。

    职责：
    1. 接收对白轨道数据。
    2. 调用 Cloud CHARACTER_PRE_ANNOTATOR 接口。
    3. 等待任务完成并下载结果。
    4. 返回增量更新数据 (包含 speaker 和 reasoning)。
    """

    @staticmethod
    def run(client: CloudApiService, local_json_path: str, asset_meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行角色识别任务。

        Args:
            client: CloudApiService 实例。
            local_json_path: 包含对白数据的临时 JSON 文件路径。
            asset_meta: 资产元数据 (video_title, known_characters, lang)。

        Returns:
            分析结果字典 (通常是包含增量更新的对白列表)。

        Raises:
            RuntimeError: 如果任务创建、执行或下载失败。
            ValueError: 如果响应中缺少下载 URL。
        """
        path_obj = Path(local_json_path)

        # 1. 执行物理化文件上传
        success, upload_result = client.upload_file(path_obj)
        if not success:
            raise RuntimeError(f"CharacterRefiner: 文件上传失败 - {upload_result}")

        # 2. 构造 Payload 并创建任务
        payload = {
            "subtitle_path": upload_result,
            "known_characters": asset_meta.get("known_characters") or [],
            "video_title": asset_meta.get("video_title"),
            "model_name": "gemini-2.5-flash",
            "lang": asset_meta.get("lang", "zh"),
        }

        api_success, task_response = client.create_task("CHARACTER_PRE_ANNOTATOR", payload)
        if not api_success:
            raise RuntimeError(f"CharacterRefiner: 任务创建失败 - {task_response}")

        # 3. 阻塞式轮询结果
        task_id = task_response.get("id")
        complete_success, final_data = client.wait_for_task_completion(task_id)

        if not complete_success:
            raise RuntimeError(f"CharacterRefiner: 云端推理失败或超时 - {final_data}")

        # 4. 下载并解析结果
        download_url = final_data.get("download_url") or final_data.get("result", {}).get("download_url")
        if not download_url:
            raise ValueError("CharacterRefiner: 任务响应中未找到下载 URL")

        dl_success, content_bytes = client.download_task_result(download_url)
        if not dl_success:
            raise RuntimeError("CharacterRefiner: 结果文件下载失败")

        return json.loads(content_bytes.decode("utf-8"))
