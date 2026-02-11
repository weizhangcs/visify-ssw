import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from apps.common.cloud_client import CloudApiService

logger = logging.getLogger(__name__)


class ScriptRefinementService:
    """
    [网络算子] 脚本精修服务 (VSS Cloud / Gemini)。
    对应 API: DUBBING_SCRIPT_REFINER (Task: REFINERY_DUBBING_SCRIPT_REFINER)

    [Output Contract]
    Result JSON structure:
    {
        "refined_script": [
            {
                "start": float, "end": float,
                "original_asr": str, "original_ocr": str,
                "refined_text": str,  # 核心产物 (Target Language)
                "source_of_truth": "ASR_OCR_MERGED" | "ASR_ONLY" | "OCR_PRIMARY" | "OCR_IGNORED" | "CONTEXT_REPAIR",
                "reasoning": str, "confidence_score": float
            }, ...
        ],
        "stats": {...},
        "usage_report": {...}
    }
    """

    @staticmethod
    def run(perception_data: Dict[str, Any], ocr_path: Optional[Path], lang: str = "zh") -> Dict[str, Any]:
        """
        Args:
            perception_data: ASR 结果 (来自 perception_meta)
            ocr_path: OCR LLM CSV 文件路径
            lang: 目标语言
        """
        client = CloudApiService()

        # 1. 准备数据 (Data Preparation)
        # 1.1 ASR Data
        asr_segments = perception_data.get("segments", [])

        # 1.2 OCR Data
        ocr_texts = []
        if ocr_path and ocr_path.exists():
            try:
                df = pd.read_csv(ocr_path)
                # 确保列名符合 API 要求: start_time, end_time, text, avg_score
                required_cols = ["start_time", "end_time", "text", "avg_score"]
                if all(col in df.columns for col in required_cols):
                    df = df.where(pd.notnull(df), None)
                    ocr_texts = df[required_cols].to_dict(orient="records")
            except Exception as e:
                logger.warning(f"ScriptRefinement: Failed to read OCR CSV {ocr_path}: {e}")

        # 2. 构造输入文件内容 (Input File Content)
        input_file_content = {"asr_segments": asr_segments, "ocr_texts": ocr_texts}

        # 3. 上传输入文件 (Upload)
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
            json.dump(input_file_content, tmp, ensure_ascii=False)
            temp_path = Path(tmp.name)

        try:
            success, upload_path = client.upload_file(temp_path)
            if not success:
                raise RuntimeError(f"ScriptRefinement: Failed to upload payload file - {upload_path}")
        finally:
            temp_path.unlink(missing_ok=True)

        # 4. 创建云端任务 (Create Task)
        # API Spec: REFINERY_DUBBING_SCRIPT_REFINER
        task_payload = {"lang": lang, "mode": "PROD", "input_file_path": upload_path}

        api_success, task_response = client.create_task("REFINERY_DUBBING_SCRIPT_REFINER", task_payload)
        if not api_success:
            raise RuntimeError(f"ScriptRefinement: Task creation failed - {task_response}")

        task_id = task_response.get("id")
        logger.info(f"ScriptRefinement: Task {task_id} created. Waiting for completion...")

        # 5. 等待并获取结果 (Wait & Download)
        complete_success, final_data = client.wait_for_task_completion(task_id)
        if not complete_success:
            raise RuntimeError(f"ScriptRefinement: Task failed or timed out - {final_data}")

        download_url = final_data.get("download_url")
        if download_url:
            dl_success, content_bytes = client.download_task_result(download_url)
            if dl_success:
                return json.loads(content_bytes.decode("utf-8"))
            else:
                raise RuntimeError(f"ScriptRefinement: Failed to download result from {download_url}")

        return final_data.get("result", {})
