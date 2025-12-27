# 文件路径: apps/refinery/services/text_analyzer.py

import logging
from typing import Dict, List

from apps.workflow.annotation.services.srt_parser import parse_srt_content

logger = logging.getLogger(__name__)


class TextAnalyzerService:
    @staticmethod
    def run(content: str) -> List[Dict]:
        """
        [物理算子] 纯粹的文本解析逻辑
        输入：字幕文件的文本内容 (String)
        输出：结构化对白列表 (List[Dict])
        """
        if not content or not content.strip():
            logger.warning("TextAnalyzer received empty content.")
            return []

        # 调用存量解析算法
        # 结果格式: [{'start': 1.0, 'end': 2.0, 'text': '...', 'speaker': '...'}]
        try:
            dialogue_list = parse_srt_content(content)
            return dialogue_list
        except Exception as e:
            logger.error(f"Logic Error in parse_srt_content: {e}")
            return []
