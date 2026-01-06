# apps/atomflow/refinery/services/visual_analyzer.py
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from apps.common.cloud_client import CloudApiService

logger = logging.getLogger(__name__)


class VisualAnalyzerService:
    """
    [Refinery Operator] 视觉分析算子 (Cloud VLM)。

    职责：
    1. 接收待分析的帧列表 (已同步到云端的路径)。
    2. 构造 Cloud API 请求 Payload。
    3. 调用 Cloud VISUAL_ANALYZER 接口。
    4. 等待任务完成并下载分析结果。
    """

    @staticmethod
    def run(
        client: CloudApiService,
        frames: List[Dict[str, Any]],
        lang: str,
        visual_model: str,
        temp_file_path: Path,
    ) -> Dict[str, Any]:
        """
        执行视觉分析任务。

        Args:
            client: CloudApiService 实例。
            frames: 帧列表，格式 [{"frame_id": "...", "path": "gs://...", "digest": "..."}]。
            lang: 目标语言代码 ("zh" or "en")。
            visual_model: 使用的 VLM 模型名称。
            temp_file_path: 用于存储 frames 数据的临时文件路径。

        Returns:
            分析结果字典 (包含 annotated_frames 列表)。

        Raises:
            RuntimeError: 如果任务创建、执行或下载失败。
        """
        if not frames:
            return {}

        # 1. 将 frames 数据写入临时文件
        try:
            with open(temp_file_path, "w", encoding="utf-8") as f:
                json.dump(frames, f, ensure_ascii=False)
        except Exception as e:
            raise RuntimeError(f"VisualAnalyzer: Failed to write temp file: {e}")

        # 2. 上传文件
        success, upload_rel_path = client.upload_file(temp_file_path)
        if not success:
            raise RuntimeError(f"VisualAnalyzer: Failed to upload frames file - {upload_rel_path}")

        # 3. 构造任务 Payload
        payload = {
            "lang": lang,
            "visual_model": visual_model,
            "frames_file_path": upload_rel_path,
        }

        # 4. 创建任务
        api_success, task_response = client.create_task("VISUAL_ANALYZER", payload)
        if not api_success:
            raise RuntimeError(f"VisualAnalyzer: Task creation failed - {task_response}")

        task_id = task_response.get("id")
        logger.info(f"VisualAnalyzer: Task {task_id} created. Waiting for completion...")

        # 5. 阻塞等待任务完成
        complete_success, final_data = client.wait_for_task_completion(task_id)
        if not complete_success:
            raise RuntimeError(f"VisualAnalyzer: Task failed or timed out - {final_data}")

        # 6. 获取结果
        result = final_data.get("result", {})

        # Case A: 结果包含 download_url (推荐)
        download_url = final_data.get("download_url")
        if download_url:
            dl_success, content_bytes = client.download_task_result(download_url)
            if not dl_success:
                raise RuntimeError("VisualAnalyzer: Failed to download result file")
            data = json.loads(content_bytes.decode("utf-8"))
            logger.info(f"VisualAnalyzer: Downloaded result keys: {list(data.keys())}")
            return data

        # Case B: 结果直接在 payload 中 (通常用于调试或小数据量)
        if "annotated_frames" in result:
            return result

        logger.warning(f"VisualAnalyzer: 'annotated_frames' not in result. Keys: {list(result.keys())}")
        return {}
