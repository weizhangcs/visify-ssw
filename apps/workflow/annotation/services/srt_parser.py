# 文件路径: apps/refinery/services/text_analyzer.py

import logging
import re
from typing import Dict, List

from .schemas import SubtitleItem

logger = logging.getLogger(__name__)


class TextAnalyzerService:
    """
    [Refinery Ingestion Operator] 文本解析标准化算子
    完全自包含：不引用外部 parse_srt_content，直接实现从原始文本到 SubtitleItem 的转化。
    """

    @staticmethod
    def run(content: str) -> List[Dict]:
        if not content or not content.strip():
            return []

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
                full_text = " ".join(lines[text_start_idx:])
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

        logger.info(f"TextAnalyzer: 解析完成，产出 {len(standardized_list)} 条标准对白")
        return standardized_list

    @staticmethod
    def _parse_time_to_seconds(time_str: str) -> float:
        """
        内部工具：将 00:00:14,333 或 00:00:14.333 转化为秒数
        """
        time_str = time_str.replace(",", ".")  # 兼容格式
        h, m, s = time_str.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
