# apps/atomflow/refinery/services/visual_analyzer.py
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from apps.workflow.common.cloud_client import CloudApiService

logger = logging.getLogger(__name__)


class VisualAnalyzerService:
    """
    [Refinery Operator] 视觉分析算子 (Cloud VLM)
    职责：
    调用 Cloud VISUAL_ANALYZER 接口，对帧列表进行分析。
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
        :param client: CloudApiService 实例
        :param frames: [{"frame_id": "...", "path": "...", "digest": "..."}]
        :param lang: "zh" or "en"
        :param visual_model: 模型名称
        :param temp_file_path: 临时文件路径，用于存储 frames 数据
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

        # 3. 构造任务 Payload (生产模式：引用文件)
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
        # [Fix] download_url is at the top level of the task response, not inside the 'result' object.
        download_url = final_data.get("download_url")
        if download_url:
            dl_success, content_bytes = client.download_task_result(download_url)
            if not dl_success:
                raise RuntimeError("VisualAnalyzer: Failed to download result file")
            data = json.loads(content_bytes.decode("utf-8"))
            logger.info(f"VisualAnalyzer: Downloaded result keys: {list(data.keys())}")
            return data

        # Case B: 结果直接在 payload 中
        if "annotated_frames" in result:
            return result

        logger.warning(f"VisualAnalyzer: 'annotated_frames' not in result. Keys: {list(result.keys())}")
        return {}
