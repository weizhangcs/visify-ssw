# 文件路径: apps/atomflow/refinery/services/character_refiner.py
import json
import logging
from pathlib import Path
from typing import Any, Dict

from apps.workflow.common.cloud_client import CloudApiService

logger = logging.getLogger(__name__)


class CharacterRefinerService:
    """
    [Refinery Operator] 角色识别纯净算子
    职责：仅负责与云端执行阻塞式同步交互，严格对齐 character_pre_annotator 接口契约。
    """

    @staticmethod
    def run(client: CloudApiService, local_json_path: str, asset_meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        :param client: 由 Context 提供的已配置好的云端客户端实例
        :param local_json_path: 由 Context 物理化后的临时 JSON 文件路径
        :param asset_meta: 包含 video_title, known_characters, lang 的元数据字典
        """

        # [核心修复] 将字符串路径转换为 Path 对象，否则调用 upload_file 会触发 'str' has no attribute 'exists'
        path_obj = Path(local_json_path)

        # 1. 执行物理化文件上传 (第1步：上传)
        success, upload_result = client.upload_file(path_obj)
        if not success:
            raise RuntimeError(f"CharacterRefiner: 文件上传失败 - {upload_result}")

        # 2. 构造 Payload 并创建任务 (对齐 character_pre_annotator 契约)
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

        # 3. 阻塞式轮询结果 (下沉至 Client 的同步等待方法)
        task_id = task_response.get("id")
        complete_success, final_data = client.wait_for_task_completion(task_id)

        if not complete_success:
            raise RuntimeError(f"CharacterRefiner: 云端推理失败或超时 - {final_data}")

        # 4. 下载并解析结果 (第4步：下载)
        download_url = final_data.get("download_url") or final_data.get("result", {}).get("download_url")
        if not download_url:
            raise ValueError("CharacterRefiner: 任务响应中未找到下载 URL")

        dl_success, content_bytes = client.download_task_result(download_url)
        if not dl_success:
            raise RuntimeError("CharacterRefiner: 结果文件下载失败")

        return json.loads(content_bytes.decode("utf-8"))
