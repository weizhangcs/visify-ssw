# apps/atomflow/refinery/services/slice_analyzer.py
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from apps.atomflow.refinery.payloads.slice_analyzer import MultimodalSlice as ExecMultimodalSlice
from apps.atomflow.refinery.payloads.slice_analyzer import SliceAnalyzerPayload, SliceAnalyzerResponse
from apps.common.cloud_client import CloudApiService

logger = logging.getLogger(__name__)


class SliceAnalyzerService:
    """
    [Refinery Operator] 切片语义分析算子 (Cloud LLM)。

    职责：
    1. [Hydration] 将 keyframe_map 中的视觉数据回填到 slices 中。
    2. 构造 Cloud API 请求 Payload (Rich Slices)。
    3. 调用 Cloud REFINERY_SLICE_ANALYZER 接口。
    4. 下载结果并回填 slice_analysis。
    """

    @staticmethod
    def run(
        client: CloudApiService,
        slices: List[Dict[str, Any]],
        keyframe_map: Dict[str, List[Dict[str, Any]]],
        dialogues: List[Dict[str, Any]],
        lang: str,
    ) -> Dict[str, Any]:
        """
        执行切片分析任务。
        """
        if not slices:
            return {"slices": []}

        # [Phase 1] Build Lookup Map for Text Hydration
        dialogue_map = {d["id"]: d for d in dialogues if d.get("id")}

        # 1. Hydration & Data Conversion
        exec_slices = []
        try:
            for s in slices:
                # 复制一份以避免修改原始引用
                s_copy = s.copy()

                # 回填视觉数据
                if keyframe_map and s_copy.get("id") in keyframe_map:
                    # [Fix] Adapt local KeyframeItem (id) to Cloud FrameDataInput (frame_id)
                    raw_frames = keyframe_map[s_copy.get("id")]
                    adapted_frames = []
                    for f in raw_frames:
                        f_adapted = f.copy()
                        if "id" in f_adapted:
                            f_adapted["frame_id"] = f_adapted.pop("id")
                        adapted_frames.append(f_adapted)
                    s_copy["visual_contents"] = adapted_frames

                # [Phase 1] Hydrate Text Data
                # 将 dialogue_ids 转换为 text_contents 实体列表
                d_ids = s_copy.get("dialogue_ids", [])
                text_contents = []
                for d_id in d_ids:
                    if d_id in dialogue_map:
                        text_contents.append(dialogue_map[d_id])
                s_copy["text_contents"] = text_contents

                # [Adapter] Flatten SliceTypeLabel to string for Cloud API
                if isinstance(s_copy.get("type"), dict):
                    s_copy["type"] = s_copy["type"].get("value")

                exec_slices.append(ExecMultimodalSlice(**s_copy))
        except Exception as e:
            raise ValueError(f"SliceAnalyzer: Data hydration/validation failed - {e}")

        # 2. 写入临时文件并上传
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
            json.dump([s.model_dump(exclude_none=True) for s in exec_slices], tmp, ensure_ascii=False)
            temp_path = Path(tmp.name)

        try:
            success, upload_path = client.upload_file(temp_path)
            if not success:
                raise RuntimeError(f"SliceAnalyzer: Failed to upload slices file - {upload_path}")
        finally:
            temp_path.unlink(missing_ok=True)

        # 3. 构造 Payload
        try:
            payload = SliceAnalyzerPayload(lang=lang, mode="PROD", slices_file_path=upload_path)
        except ValueError as e:
            raise ValueError(f"SliceAnalyzer: Payload validation failed - {e}")

        # 4. 创建任务
        api_success, task_response = client.create_task(
            "REFINERY_SLICE_ANALYZER", payload.model_dump(exclude_none=True)
        )
        if not api_success:
            raise RuntimeError(f"SliceAnalyzer: Task creation failed - {task_response}")

        task_id = task_response.get("id")
        logger.info(f"SliceAnalyzer: Task {task_id} created. Waiting for completion...")

        # 5. 等待结果
        complete_success, final_data = client.wait_for_task_completion(task_id)
        if not complete_success:
            raise RuntimeError(f"SliceAnalyzer: Task failed or timed out - {final_data}")

        # 6. 下载结果
        download_url = final_data.get("download_url")
        if not download_url:
            raise RuntimeError("SliceAnalyzer: Task completed but no download_url provided.")

        dl_success, content_bytes = client.download_task_result(download_url)
        if not dl_success:
            raise RuntimeError(f"SliceAnalyzer: Failed to download result file from {download_url}")

        try:
            # Use Pydantic validation
            response = SliceAnalyzerResponse.model_validate_json(content_bytes.decode("utf-8"))
            analyzed_slices = response.analyzed_slices

            # 7. Merge Analysis back to Hydrated Slices
            # 我们需要返回包含 visual_contents 和 slice_analysis 的完整切片
            analysis_map = {item.id: item.slice_analysis.model_dump() for item in analyzed_slices}

            final_slices = []
            # [Fix] 遍历原始 slices 以保留本地数据结构 (LabelValue type, reference IDs)
            # 不要使用 exec_slices，因为它已经丢失了本地字段且 type 被扁平化了
            for s in slices:
                s_dict = s.copy()
                s_id = s_dict.get("id")
                if s_id in analysis_map:
                    s_dict["slice_analysis"] = analysis_map[s_id]
                final_slices.append(s_dict)

            return {"slices": final_slices}

        except Exception as e:
            raise RuntimeError(f"SliceAnalyzer: Failed to process result JSON: {e}")
