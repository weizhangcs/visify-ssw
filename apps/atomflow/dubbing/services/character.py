import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from apps.common.cloud_client import CloudApiService

logger = logging.getLogger(__name__)


class CharacterRoleFinalizerService:
    """
    [网络算子] 角色定稿服务 (VSS Cloud / Gemini)。
    对应 API: REFINERY_CHARACTER_ROLE_FINALIZER

    该服务位于物理感知层之后，利用 LLM 对物理 ID (PERSON_00) 进行逻辑校验和实体归一化。
    """

    @staticmethod
    def run(fusion_data: List[Dict[str, Any]], lang: str = "zh") -> Dict[str, Any]:
        """
        Args:
            fusion_data: Fusion 服务的产出物 (List of segments with speaker ID & fusion_score)
            lang: 目标语言
        """
        client = CloudApiService()

        # 0. 数据规范校对 (Data Validation & Sanitization)
        # 确保发送给云端的数据严格符合 API 规范，去除无关字段，防止校验失败
        clean_segments = []
        for item in fusion_data:
            # 必须包含时间轴
            if "start" not in item or "end" not in item:
                continue

            clean_item = {
                "start": float(item.get("start", 0.0)),
                "end": float(item.get("end", 0.0)),
                "refined_text": str(item.get("refined_text") or ""),
                "speaker": str(item.get("speaker") or "UNKNOWN"),
                "fusion_score": float(item.get("fusion_score", 0.0)),
            }
            clean_segments.append(clean_item)

        # 1. 构造输入文件内容
        # API 支持直接传入对象列表或包含 segments 的字典
        input_file_content = {"segments": clean_segments}

        # 2. 上传输入文件 (Upload)
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
            json.dump(input_file_content, tmp, ensure_ascii=False)
            temp_path = Path(tmp.name)

        upload_path = None
        try:
            success, upload_path = client.upload_file(temp_path)
            if not success:
                raise RuntimeError(f"CharacterRoleFinalizer: Failed to upload payload file - {upload_path}")
        finally:
            temp_path.unlink(missing_ok=True)

        # 3. 创建云端任务 (Create Task)
        # API Spec: REFINERY_CHARACTER_ROLE_FINALIZER
        task_payload = {"lang": lang, "mode": "PROD", "input_file_path": upload_path}

        api_success, task_response = client.create_task("REFINERY_CHARACTER_ROLE_FINALIZER", task_payload)
        if not api_success:
            raise RuntimeError(f"CharacterRoleFinalizer: Task creation failed - {task_response}")

        task_id = task_response.get("id")
        logger.info(f"CharacterRoleFinalizer: Task {task_id} created. Waiting for completion...")

        # 4. 等待并获取结果 (Wait & Download)
        complete_success, final_data = client.wait_for_task_completion(task_id)
        if not complete_success:
            raise RuntimeError(f"CharacterRoleFinalizer: Task failed or timed out - {final_data}")

        download_url = final_data.get("download_url")
        if download_url:
            dl_success, content_bytes = client.download_task_result(download_url)
            if dl_success:
                return json.loads(content_bytes.decode("utf-8"))
            else:
                raise RuntimeError(f"CharacterRoleFinalizer: Failed to download result from {download_url}")

        # 如果没有 download_url，尝试直接返回 result 字段 (视 API 具体行为而定)
        return final_data.get("result", {})
