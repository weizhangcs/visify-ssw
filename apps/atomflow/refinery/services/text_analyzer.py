# 文件路径: apps/atomflow/refinery/services/text_analyzer.py

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from apps.workflow.common.cloud_client import CloudApiService

# [修正] 引用新位置的 schemas
from ..schemas import SubtitleItem

logger = logging.getLogger(__name__)


class TextAnalyzerService:
    """
    [Refinery Ingestion Operator] 文本解析标准化算子
    完全自包含：不引用外部 parse_srt_content，直接实现从原始文本到 SubtitleItem 的转化。
    """

    @staticmethod
    def run(
        content: str,
        cloud_client: Optional[CloudApiService] = None,
        temp_file_path: Optional[Path] = None,
        enable_semantic_merge: bool = True,
        lang: str = "zh",
        model_name: str = "models/gemini-2.5-flash",
    ) -> List[Dict]:
        if not content or not content.strip():
            return []

        # [New] 前置清洗：编码、标签、环境音
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
                # [New] 使用智能合并逻辑替代简单的 " ".join
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
                # 这一步会自动校验字段：index, content, start_time, end_time, speaker
                item = SubtitleItem(
                    index=index_counter, content=clean_content, start_time=start_sec, end_time=end_sec, speaker=speaker
                )

                standardized_list.append(item.model_dump())
                index_counter += 1

            except Exception as e:
                # 记录具体哪一块解析出错，但不中断整体流程，除非全是错的
                logger.warning(f"TextAnalyzer: 忽略异常格式块: {e}")
                continue

        # [New] 场景 3: 语义合并 (LLM)
        if enable_semantic_merge and cloud_client and temp_file_path and standardized_list:
            logger.info("TextAnalyzer: 启动语义合并流程...")
            merged_list = TextAnalyzerService._semantic_merge_subtitles(
                cloud_client, standardized_list, temp_file_path, lang, model_name
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
        [清洗管道] 对原始 SRT 文本进行预处理
        1. 去除 BOM 头
        2. 去除 HTML 样式标签 (<b>, <i>, <font> 等)
        3. 去除 ASS/SSA 风格控制符 ({\an8} 等)
        4. 去除环境音/听障辅助标识 ([...], (...))
        """
        # 1. 去除 BOM
        content = content.lstrip("\ufeff")

        # 2. 去除 HTML 标签 (非贪婪匹配)
        # e.g., <b>Hello</b> -> Hello, <br> -> ""
        content = re.sub(r"<[^>]+>", "", content)

        # 3. 去除 ASS 风格控制符
        # e.g., {\an8} -> ""
        content = re.sub(r"\{[^}]+\}", "", content)

        # 4. 去除环境音/备注 (策略 A: 清洗)
        # e.g., [Music playing], (Applause)
        # 注意：这里假设 [] 和 () 内全是噪音。如果对白中有括号补充说明，也会被误删。
        # 但在 SRT 标准对白中，这通常是安全的假设。
        content = re.sub(r"\[[^\]]+\]", "", content)
        content = re.sub(r"\([^)]+\)", "", content)

        return content

    @staticmethod
    def _merge_lines_smartly(lines: List[str]) -> str:
        """
        [智能合并] 合并多行字幕，避免中文之间出现不必要的空格
        """
        if not lines:
            return ""

        result = lines[0]
        for line in lines[1:]:
            # 如果前一行结尾是中文，且当前行开头是中文，则直接拼接
            # 简单判断：Unicode 范围 \u4e00-\u9fa5
            if result and line and "\u4e00" <= result[-1] <= "\u9fa5" and "\u4e00" <= line[0] <= "\u9fa5":
                result += line
            else:
                result += " " + line
        return result.strip()

    @staticmethod
    def _parse_time_to_seconds(time_str: str) -> float:
        """
        内部工具：将 00:00:14,333 或 00:00:14.333 转化为秒数
        """
        time_str = time_str.replace(",", ".")  # 兼容格式
        h, m, s = time_str.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    @staticmethod
    def _semantic_merge_subtitles(
        client: CloudApiService, subtitles: List[Dict], temp_file_path: Path, lang: str, model_name: str
    ) -> List[Dict]:
        """
        调用 Cloud SUBTITLE_MERGER 接口进行语义合并
        """
        # 1. 写入临时文件
        try:
            with open(temp_file_path, "w", encoding="utf-8") as f:
                json.dump(subtitles, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"TextAnalyzer: Failed to write temp file for merge: {e}")
            return []

        # 2. 上传文件
        success, upload_rel_path = client.upload_file(temp_file_path)
        if not success:
            logger.error(f"TextAnalyzer: Failed to upload subtitles file - {upload_rel_path}")
            return []

        # 3. 构造 Payload (生产模式)
        payload = {
            "lang": lang,
            "model": model_name,
            "subtitle_file_path": upload_rel_path,
        }

        # 4. 创建任务
        api_success, task_response = client.create_task("SUBTITLE_MERGER", payload)
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
        # 结果通常包含 download_url
        download_url = final_data.get("download_url") or final_data.get("result", {}).get("download_url")
        if download_url:
            dl_success, content_bytes = client.download_task_result(download_url)
            if dl_success:
                result_json = json.loads(content_bytes.decode("utf-8"))
                return result_json.get("merged_subtitles", [])

        # Fallback: 检查 result 中是否直接包含数据 (调试模式可能发生)
        return final_data.get("result", {}).get("merged_subtitles", [])
