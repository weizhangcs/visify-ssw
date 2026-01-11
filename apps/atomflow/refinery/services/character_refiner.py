# 文件路径: apps/atomflow/refinery/services/character_refiner.py
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from apps.common.cloud_client import CloudApiService
from apps.common.schemas.refinery.character_identifier import AudioAnalysis as ExecAudioAnalysis
from apps.common.schemas.refinery.character_identifier import CharacterIdentifierPayload
from apps.common.schemas.refinery.character_identifier import SubtitleItem as ExecSubtitleItem

logger = logging.getLogger(__name__)


class CharacterRefinerService:
    """
    [Refinery Operator] 角色识别算子 (Cloud LLM)。
    调用 Cloud REFINERY_CHARACTER_IDENTIFIER 接口。
    """

    @staticmethod
    def run(client: CloudApiService, dialogue_data: List[Dict], asset_meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行角色识别任务。

        Args:
            client: CloudApiService 实例。
            dialogue_data: 对白轨道数据列表。
            asset_meta: 资产元数据 (video_title, known_characters, lang)。

        Returns:
            分析结果字典 (包含 identified_subtitles)。
        """
        if not dialogue_data:
            logger.warning("CharacterRefiner: No dialogue data provided.")
            return {"identified_subtitles": []}

        # 1. 数据转换 (Dict -> Execution Schema)
        exec_items = []
        for item in dialogue_data:
            # 处理多模态音频分析数据
            audio_analysis = None
            if item.get("audio_analysis"):
                audio_analysis = ExecAudioAnalysis(gender=item["audio_analysis"].get("gender", "Unknown"))

            exec_items.append(
                ExecSubtitleItem(
                    index=item["index"],
                    start_time=item["start_time"],
                    end_time=item["end_time"],
                    content=item["content"],
                    audio_analysis=audio_analysis,
                )
            )

        # 2. 写入临时文件并上传
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json", encoding="utf-8") as tmp:
            # exclude_none=True 确保不发送空字段
            json.dump([i.model_dump(exclude_none=True) for i in exec_items], tmp, ensure_ascii=False)
            temp_path = Path(tmp.name)

        try:
            success, upload_path = client.upload_file(temp_path)
            if not success:
                raise RuntimeError(f"CharacterRefiner: 文件上传失败 - {upload_path}")
        finally:
            temp_path.unlink(missing_ok=True)

        # 3. 构造 Payload (使用 Schema 校验)
        try:
            payload = CharacterIdentifierPayload(
                lang=asset_meta.get("lang", "zh"),
                mode="PROD",
                subtitle_file_path=upload_path,
                known_characters=asset_meta.get("known_characters") or [],
                video_title=asset_meta.get("video_title"),
            )
        except ValueError as e:
            raise ValueError(f"CharacterRefiner: Payload 校验失败 - {e}")

        # 4. 创建任务
        api_success, task_response = client.create_task(
            "REFINERY_CHARACTER_IDENTIFIER", payload.model_dump(exclude_none=True)
        )
        if not api_success:
            raise RuntimeError(f"CharacterRefiner: 任务创建失败 - {task_response}")

        # 5. 阻塞式轮询结果
        task_id = task_response.get("id")
        complete_success, final_data = client.wait_for_task_completion(task_id)

        if not complete_success:
            raise RuntimeError(f"CharacterRefiner: 云端推理失败或超时 - {final_data}")

        # 6. 下载并解析结果
        # VSS Cloud 返回标准: 顶层 download_url 用于下载结果文件
        # output_file_path 是云端相对路径，仅用于云端任务链式引用，不用于直接下载
        download_url = final_data.get("download_url")

        if not download_url:
            raise ValueError("CharacterRefiner: 任务响应中未找到下载 URL")

        dl_success, content_bytes = client.download_task_result(download_url)
        if not dl_success:
            raise RuntimeError(f"CharacterRefiner: 结果下载失败 - {download_url}")

        return json.loads(content_bytes.decode("utf-8"))
