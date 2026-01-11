# 文件路径: apps/atomflow/refinery/services/text_analyzer.py

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from apps.common.cloud_client import CloudApiService
from apps.common.schemas.refinery.subtitle_merger import SubtitleItem as ExecSubtitleItem
from apps.common.schemas.refinery.subtitle_merger import SubtitleMergerPayload

# 持久化 Schema (用于 Material.dialogue 存储)
from ..schemas import SubtitleItem

logger = logging.getLogger(__name__)


class TextAnalyzerService:
    """
    [Refinery Ingestion Operator] 文本解析标准化算子。

    职责：
    1. 解析原始字幕文本 (SRT/VTT 风格)。
    2. 清洗文本内容 (去除标签、特效符、环境音)。
    3. 智能合并断句 (针对中文优化)。
    4. 转换为标准的 SubtitleItem 结构。
    5. (可选) 调用 Cloud API 进行语义级合并。
    """

    @staticmethod
    def run(
        content: str,
        cloud_client: Optional[CloudApiService] = None,
        temp_file_path: Optional[Path] = None,
        enable_semantic_merge: bool = True,
        lang: str = "zh",
    ) -> List[Dict]:
        """
        执行文本解析任务。

        Args:
            content: 原始字幕文本内容。
            cloud_client: CloudApiService 实例 (用于语义合并)。
            temp_file_path: 临时文件路径 (用于语义合并上传)。
            enable_semantic_merge: 是否启用语义合并。
            lang: 语言代码。

        Returns:
            标准化对白列表 (List[SubtitleItem.model_dump()])。
        """
        if not content or not content.strip():
            return []

        # 前置清洗：编码、标签、环境音
        content = TextAnalyzerService._preprocess_content(content)

        # 1. 规范化换行并切割块
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        # 兼容处理：支持多换行符切割
        blocks = re.split(r"\n\s*\n", content.strip())

        standardized_list = []
        index_counter = 0

        for block in blocks:
            lines = [l.strip() for l in block.split("\n") if l.strip()]  # noqa: E741
            if len(lines) < 2:
                continue

            # 2. 寻找时间轴行 (例如: 00:00:14,333 --> 00:00:16,541)
            time_line = ""
            text_start_idx = 0
            for i, line in enumerate(lines):
                if " --> " in line:
                    time_line = line
                    text_start_idx = i + 1
                    break

            if not time_line or text_start_idx >= len(lines):
                continue

            try:
                # 3. 解析时间戳
                start_str, end_str = time_line.split(" --> ")
                start_sec = TextAnalyzerService._parse_time_to_seconds(start_str)
                end_sec = TextAnalyzerService._parse_time_to_seconds(end_str)

                # 4. 提取文本内容并尝试分离角色
                # 使用智能合并逻辑替代简单的 " ".join
                raw_lines = lines[text_start_idx:]
                full_text = TextAnalyzerService._merge_lines_smartly(raw_lines)
                speaker = "Unknown"
                clean_content = full_text

                # 兼容中文和英文冒号的角色提取
                if "：" in full_text:
                    parts = full_text.split("：", 1)
                    speaker, clean_content = parts[0].strip(), parts[1].strip()
                elif ":" in full_text:
                    parts = full_text.split(":", 1)
                    speaker, clean_content = parts[0].strip(), parts[1].strip()

                # 5. 构造强契约 SubtitleItem
                item = SubtitleItem(
                    index=index_counter, content=clean_content, start_time=start_sec, end_time=end_sec, speaker=speaker
                )

                standardized_list.append(item.model_dump())
                index_counter += 1

            except Exception as e:
                logger.warning(f"TextAnalyzer: 忽略异常格式块: {e}")
                continue

        # 场景 3: 语义合并 (LLM)
        if enable_semantic_merge and cloud_client and temp_file_path and standardized_list:
            logger.info("TextAnalyzer: 启动语义合并流程...")
            merged_list = TextAnalyzerService._semantic_merge_subtitles(
                cloud_client, standardized_list, temp_file_path, lang
            )
            if merged_list:
                logger.info(f"TextAnalyzer: 语义合并完成，条目数从 {len(standardized_list)} 优化为 {len(merged_list)}")
                return merged_list
            else:
                logger.warning("TextAnalyzer: 语义合并未返回有效结果，回退至原始列表")

        logger.info(f"TextAnalyzer: 解析完成，产出 {len(standardized_list)} 条标准对白")
        return standardized_list

    @staticmethod
    def _preprocess_content(content: str) -> str:
        """
        [内部方法] 对原始 SRT 文本进行预处理。
        1. 去除 BOM 头。
        2. 去除 HTML 样式标签 (<b>, <i>, <font> 等)。
        3. 去除 ASS/SSA 风格控制符 ({\an8} 等)。
        4. 去除环境音/听障辅助标识 ([...], (...))。
        """
        # 1. 去除 BOM
        content = content.lstrip("\ufeff")

        # 2. 去除 HTML 标签 (非贪婪匹配)
        content = re.sub(r"<[^>]+>", "", content)

        # 3. 去除 ASS 风格控制符
        content = re.sub(r"\{[^}]+\}", "", content)

        # 4. 去除环境音/备注
        content = re.sub(r"\[[^\]]+\]", "", content)
        content = re.sub(r"\([^)]+\)", "", content)

        return content

    @staticmethod
    def _merge_lines_smartly(lines: List[str]) -> str:
        """
        [内部方法] 智能合并多行字幕。
        避免中文之间出现不必要的空格，同时保留英文单词间的空格。
        """
        if not lines:
            return ""

        result = lines[0]
        for line in lines[1:]:
            # 如果前一行结尾是中文，且当前行开头是中文，则直接拼接
            if result and line and "\u4e00" <= result[-1] <= "\u9fa5" and "\u4e00" <= line[0] <= "\u9fa5":
                result += line
            else:
                result += " " + line
        return result.strip()

    @staticmethod
    def _parse_time_to_seconds(time_str: str) -> float:
        """
        [内部方法] 将时间字符串 (00:00:14,333) 转化为秒数 (float)。
        """
        time_str = time_str.replace(",", ".")  # 兼容格式
        h, m, s = time_str.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    @staticmethod
    def _semantic_merge_subtitles(
        client: CloudApiService, subtitles: List[Dict], temp_file_path: Path, lang: str
    ) -> List[Dict]:
        """
        [内部方法] 调用 Cloud REFINERY_SUBTITLE_MERGER 接口进行语义合并。
        """
        # 1. 转换并写入临时文件 (使用 Execution Schema)
        try:
            # 将持久化格式转换为执行格式 (虽然结构相似，但为了严谨进行转换)
            exec_items = [
                ExecSubtitleItem(
                    index=s["index"],
                    start_time=s["start_time"],
                    end_time=s["end_time"],
                    content=s["content"],
                )
                for s in subtitles
            ]
            with open(temp_file_path, "w", encoding="utf-8") as f:
                json.dump([item.model_dump() for item in exec_items], f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"TextAnalyzer: Failed to write temp file for merge: {e}")
            return []

        # 2. 上传文件
        success, upload_rel_path = client.upload_file(temp_file_path)
        if not success:
            logger.error(f"TextAnalyzer: Failed to upload subtitles file - {upload_rel_path}")
            return []

        # 3. 构造 Payload (使用 Pydantic 校验)
        try:
            payload = SubtitleMergerPayload(lang=lang, mode="DEBUG", subtitle_file_path=upload_rel_path)
        except ValueError as e:
            logger.error(f"TextAnalyzer: Invalid payload: {e}")
            return []

        # 4. 创建任务
        # exclude_none=True 确保不发送多余的 null 字段
        api_success, task_response = client.create_task(
            "REFINERY_SUBTITLE_MERGER", payload.model_dump(exclude_none=True)
        )
        if not api_success:
            logger.error(f"TextAnalyzer: Merge task creation failed - {task_response}")
            return []

        task_id = task_response.get("id")
        logger.info(f"TextAnalyzer: Merge Task {task_id} created. Waiting...")

        # 5. 等待结果
        complete_success, final_data = client.wait_for_task_completion(task_id)
        if not complete_success:
            logger.error(f"TextAnalyzer: Merge task failed or timed out - {final_data}")
            return []

        # 6. 下载结果
        # VSS Cloud 返回标准: 顶层 download_url 用于下载结果文件
        # output_file_path 是云端相对路径，仅用于云端任务链式引用，不用于直接下载
        download_url = final_data.get("download_url")

        if download_url:
            dl_success, content_bytes = client.download_task_result(download_url)
            if dl_success:
                try:
                    result_json = json.loads(content_bytes.decode("utf-8"))
                    return result_json.get("merged_subtitles", [])
                except Exception as e:
                    logger.error(f"TextAnalyzer: Failed to parse result JSON: {e}")
                    return []
            else:
                logger.error(f"TextAnalyzer: Failed to download result from {download_url}")
                return []

        return final_data.get("result", {}).get("merged_subtitles", [])
