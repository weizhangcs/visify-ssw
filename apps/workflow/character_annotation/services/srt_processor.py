# 文件路径: apps/workflow/character_annotation/services/srt_processor.py

import logging
import re
from typing import Dict, List

logger = logging.getLogger(__name__)


class SRTBatchProcessor:
    """
    (V1.0 - 范式对齐版)
    负责处理角色预标注过程中的字幕合并与结果分发逻辑。
    """

    def __init__(self):
        # 内部映射表: { global_index: media_id }
        self.index_map = {}
        self.current_global_index = 1

    def merge_srts(self, srt_inputs: List[Dict]) -> str:
        """
        将多个 Media 的 SRT 内容合并为一个用于云端推理的大文本。
        :param srt_inputs: List[{"media_id": str, "content": str}]
        :return: 合并后的 SRT 字符串
        """
        merged_output = []
        self.index_map = {}
        self.current_global_index = 1

        # 匹配 SRT 块的正则: 1\n00:00:00,000 --> 00:00:00,000\nText...
        srt_block_pattern = re.compile(
            r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\n((?:.|[\r\n])*?)(?=\n\n|\Z)", re.MULTILINE
        )

        for item in srt_inputs:
            media_id = str(item["media_id"])
            content = item["content"].replace("\r\n", "\n").strip() + "\n\n"

            matches = srt_block_pattern.findall(content)

            for _, time_range, text in matches:
                # 建立全局行号与原始 Media 的映射关系
                self.index_map[self.current_global_index] = media_id

                # 重新编号，构建合并后的块
                block = f"{self.current_global_index}\n{time_range}\n{text}"
                merged_output.append(block)

                self.current_global_index += 1

        return "\n\n".join(merged_output)

    def generate_ass_files(self, cloud_response_data: Dict) -> Dict[str, str]:
        """
        解析云端返回的 optimized_subtitles 数据，并根据 index_map 拆分回各个 Media。
        :param cloud_response_data: 云端返回的 JSON 字典，包含 "optimized_subtitles" 列表
        :return: Dict { media_id: "ass_content_string" }
        """
        subtitles = cloud_response_data.get("optimized_subtitles", [])

        # 按 media_id 分组存储字幕行
        grouped_lines = {}  # { media_id: [line_dict, ...] }

        for item in subtitles:
            idx = item.get("index")
            media_id = self.index_map.get(idx)

            if not media_id:
                logger.warning(f"Index {idx} not in current session map, skipping.")
                continue

            if media_id not in grouped_lines:
                grouped_lines[media_id] = []

            grouped_lines[media_id].append(item)

        # 为每个 media 构造完整的 ASS 文本
        results = {}
        for media_id, lines in grouped_lines.items():
            results[media_id] = self._build_ass_text(lines)

        return results

    def _build_ass_text(self, lines: List[Dict]) -> str:
        """
        内部辅助方法：将 JSON 字幕行序列化为标准 ASS 格式。
        """
        header = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"  # noqa:E501,E121
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n"  # noqa:E501,E121
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        events = []
        for line in lines:
            start = self._format_ass_time(line.get("start_time", 0))
            end = self._format_ass_time(line.get("end_time", 0))
            speaker = line.get("speaker", "Unknown")
            content = line.get("content", "").replace("\n", "\\N")

            # 范式说明：我们将 speaker 存入 ASS 的 Name 字段
            event_line = f"Dialogue: 0,{start},{end},Default,{speaker},0,0,0,,{content}"  # noqa: E231
            events.append(event_line)

        return header + "\n".join(events)

    def _format_ass_time(self, seconds: float) -> str:
        """将秒数转换为 ASS 时间格式 H:MM:SS.cs"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int(round((seconds - int(seconds)) * 100))
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"  # noqa: E231
