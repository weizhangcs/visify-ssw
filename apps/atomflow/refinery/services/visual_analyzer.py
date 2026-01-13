# apps/atomflow/refinery/services/visual_analyzer.py
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from apps.common.cloud_client import CloudApiService
from apps.common.schemas.refinery.visual_analyzer import VisualAnalyzerPayload, VisualAnalyzerResponse
from apps.common.schemas.refinery.visual_analyzer import VisualFrameInput as ExecVisualFrameInput

logger = logging.getLogger(__name__)


class VisualAnalyzerService:
    """
    [Refinery Operator] 视觉分析算子 (Cloud VLM)。

    职责：
    1. 接收待分析的帧列表 (包含云端路径)。
    2. 构造 Cloud API 请求 Payload。
    3. 调用 Cloud VISUAL_ANALYZER 接口。
    4. 等待任务完成并下载分析结果。
    """

    @staticmethod
    def run(
        client: CloudApiService,
        frames: List[Dict[str, Any]],
        lang: str,
    ) -> VisualAnalyzerResponse:
        """
        执行视觉分析任务。

        Args:
            client: CloudApiService 实例。
            frames: 帧列表，格式 [{"frame_id": "...", "path": "gs://...", "digest": "..."}]。
            lang: 目标语言代码 ("zh" or "en")。

        Returns:
            VisualAnalyzerResponse 对象。

        Raises:
            RuntimeError: 如果任务创建、执行或下载失败。
        """
        if not frames:
            return {}

        # 1. 数据转换 (Dict -> Execution Schema)
        exec_frames = []
        for f in frames:
            exec_frames.append(
                ExecVisualFrameInput(
                    frame_id=f["frame_id"],
                    path=f["path"],  # 这里的 path 应该是云端路径 (gs:// 或 http://)
                    digest=f.get("digest"),
                )
            )

        # 2. 写入临时文件并上传
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
            # exclude_none=True 确保不发送空字段
            json.dump([f.model_dump(exclude_none=True) for f in exec_frames], tmp, ensure_ascii=False)
            temp_path = Path(tmp.name)

        try:
            success, upload_path = client.upload_file(temp_path)
            if not success:
                raise RuntimeError(f"VisualAnalyzer: Failed to upload frames file - {upload_path}")
        finally:
            temp_path.unlink(missing_ok=True)

        # 3. 构造任务 Payload
        try:
            payload = VisualAnalyzerPayload(
                lang=lang,
                mode="PROD",
                frames_file_path=upload_path,
            )
        except ValueError as e:
            raise ValueError(f"VisualAnalyzer: Payload validation failed - {e}")

        # 4. 创建任务
        api_success, task_response = client.create_task(
            "REFINERY_VISUAL_ANALYZER", payload.model_dump(exclude_none=True)
        )
        if not api_success:
            raise RuntimeError(f"VisualAnalyzer: Task creation failed - {task_response}")

        task_id = task_response.get("id")
        logger.info(f"VisualAnalyzer: Task {task_id} created. Waiting for completion...")

        # 5. 阻塞等待任务完成
        complete_success, final_data = client.wait_for_task_completion(task_id)
        if not complete_success:
            raise RuntimeError(f"VisualAnalyzer: Task failed or timed out - {final_data}")

        # 6. 获取结果
        # result = final_data.get("result", {})

        # VSS Cloud 返回标准: 顶层 download_url 用于下载结果文件
        download_url = final_data.get("download_url")

        if download_url:
            dl_success, content_bytes = client.download_task_result(download_url)
            if not dl_success:
                raise RuntimeError(f"VisualAnalyzer: Failed to download result file from {download_url}")

            # Use Pydantic validation
            return VisualAnalyzerResponse.model_validate_json(content_bytes.decode("utf-8"))

        raise RuntimeError("VisualAnalyzer: Task completed but no download_url provided.")
