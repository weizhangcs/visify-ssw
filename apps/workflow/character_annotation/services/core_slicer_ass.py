import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MockSubItem:
    """模拟字幕条目对象，用于内部逻辑流转"""

    def __init__(self, start_sec, end_sec, text):
        # 模拟 pysubs2 或类似库的结构，单位转为 ms
        self.start = type("obj", (object,), {"ordinal": int(start_sec * 1000)})
        self.end = type("obj", (object,), {"ordinal": int(end_sec * 1000)})
        self.text = text


class VSSASSSlicer:
    """
    [Core Algorithm] ASS 专用智能切片器
    职责：读取视频和ASS，输出切片的时间轴清单 (Slices Manifest)
    """

    def __init__(self, video_path: str, ass_path: str):
        self.video_path = Path(video_path)
        self.subtitle_path = Path(ass_path)
        self.ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_bin = shutil.which("ffprobe") or "ffprobe"

        # 核心参数 (可配置)
        self.MIN_VISUAL_DURATION = 2.0  # 最小视觉片段时长 (秒)
        self.SCENE_THRESHOLD = 0.3  # ffmpeg场景检测阈值 (0-1)

    def _parse_ass_time(self, time_str):
        """解析 ASS 时间格式 H:MM:SS.cc -> 秒"""
        try:
            parts = time_str.split(":")
            h, m = int(parts[0]), int(parts[1])
            s, cs = map(int, parts[2].split("."))
            return h * 3600 + m * 60 + s + (cs / 100.0)
        except Exception:
            return 0.0

    def load_subs_from_ass(self) -> List[MockSubItem]:
        """解析 ASS 字幕文件"""
        subs = []
        if not self.subtitle_path.exists():
            logger.error(f"ASS file not found: {self.subtitle_path}")
            return subs

        try:
            with open(self.subtitle_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # 解析 Dialogue 行
            # Format: Dialogue: 0,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
            for line in lines:
                if line.startswith("Dialogue:"):
                    parts = line.split(",", 9)
                    if len(parts) >= 10:
                        start_sec = self._parse_ass_time(parts[1].strip())
                        end_sec = self._parse_ass_time(parts[2].strip())
                        speaker = parts[4].strip()
                        content = parts[9].strip().replace("\\N", " ")

                        # 组合角色与文本，用于后续Context辅助
                        full_text = f"[{speaker}]: {content}"
                        subs.append(MockSubItem(start_sec, end_sec, full_text))

            # 按时间排序
            subs.sort(key=lambda x: x.start.ordinal)
            return subs
        except Exception as e:
            logger.error(f"Failed to parse ASS: {e}")
            return []

    def _run_ffmpeg_filter(self, filter_chain: str) -> str:
        """运行 ffmpeg filter 获取场景变更点 (Debug版)"""
        cmd = [
            self.ffmpeg_bin,
            "-i",
            str(self.video_path),
            "-filter_complex",
            filter_chain,
            "-map",
            "[outv]",
            "-f",
            "null",
            "-",
        ]

        # [Debug] 打印实际执行的命令，方便手动复现
        logger.info(f"FFmpeg CMD: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, encoding="utf-8", errors="ignore"
            )
            _, stderr = process.communicate()

            # [Fix] 检查返回值，如果非0，说明 FFmpeg 报错了
            if process.returncode != 0:
                logger.error(f"❌ FFmpeg CRASHED (Return Code {process.returncode}): ")
                logger.error(stderr)  # 打印具体的错误堆栈
                return ""

            return stderr
        except Exception as e:
            logger.error(f"FFmpeg execution failed: {e}")
            return ""

    def detect_scene_changes(self) -> List[float]:
        """使用 ffmpeg 探测视觉转场点"""
        logger.info(f"Running Scene Detection (threshold={self.SCENE_THRESHOLD})...")
        # select filter 选出变化大的帧，showinfo 打印时间戳
        filter_cmd = f"select='gt(scene,{self.SCENE_THRESHOLD})',showinfo"  # noqa E231
        log = self._run_ffmpeg_filter(f"[0:v]{filter_cmd}[outv]")

        timestamps = []
        for line in log.splitlines():
            if "pts_time:" in line and "showinfo" in line:
                match = re.search(r"pts_time:([0-9.]+)", line)
                if match:
                    timestamps.append(float(match.group(1)))

        unique_ts = sorted(list(set(timestamps)))
        logger.info(f"Detected {len(unique_ts)} scene changes.")
        return unique_ts

    def get_video_duration(self) -> float:
        cmd = [
            self.ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(self.video_path),
        ]
        try:
            return float(subprocess.check_output(cmd).decode().strip())
        except Exception:
            return 0.0

    def compute_slices(self) -> Dict[str, Any]:
        """
        主计算流程：合并字幕时间轴与视觉转场信号
        返回: { "total_duration": float, "slices": [...] }
        """
        duration = self.get_video_duration()
        scene_changes = self.detect_scene_changes()
        subs = self.load_subs_from_ass()

        slices = []
        last_time = 0.0

        logger.info(f"Merging signals ({len(subs)} dialogue lines) into slices...")

        for sub in subs:
            start_sec = sub.start.ordinal / 1000.0
            end_sec = sub.end.ordinal / 1000.0
            text_content = sub.text

            # --- Logic A: Gap Filling (视觉空隙填充) ---
            # 如果两条字幕之间有足够长的空白，尝试利用 ffmpeg 检测到的转场点切分纯视觉片段
            if start_sec > last_time:
                gap_start = last_time
                gap_end = start_sec
                gap_duration = gap_end - gap_start

                if gap_duration >= self.MIN_VISUAL_DURATION:
                    # 寻找落在这个 Gap 内部的转场点
                    internal_cuts = [t for t in scene_changes if gap_start + 0.5 < t < gap_end - 0.5]

                    if internal_cuts:
                        # 如果有转场点，将 Gap 切细
                        current_gap_ptr = gap_start
                        for cut in internal_cuts:
                            slices.append(
                                {
                                    "start_time": round(current_gap_ptr, 3),
                                    "end_time": round(cut, 3),
                                    "type": "visual_segment",
                                    "text_content": None,
                                }
                            )
                            current_gap_ptr = cut
                        # 收尾最后一段
                        slices.append(
                            {
                                "start_time": round(current_gap_ptr, 3),
                                "end_time": round(gap_end, 3),
                                "type": "visual_segment",
                                "text_content": None,
                            }
                        )
                    else:
                        # 没有转场点，整个 Gap 算一段
                        slices.append(
                            {
                                "start_time": round(gap_start, 3),
                                "end_time": round(gap_end, 3),
                                "type": "visual_segment",
                                "text_content": None,
                            }
                        )

            # --- Logic B: Dialogue (字幕片段) ---
            slices.append(
                {
                    "start_time": round(start_sec, 3),
                    "end_time": round(end_sec, 3),
                    "type": "dialogue",
                    "text_content": text_content,
                }
            )
            last_time = end_sec

        # --- Logic C: Tail Gap (片尾空隙) ---
        if last_time < duration:
            if duration - last_time >= self.MIN_VISUAL_DURATION:
                slices.append(
                    {
                        "start_time": round(last_time, 3),
                        "end_time": round(duration, 3),
                        "type": "visual_segment",
                        "text_content": None,
                    }
                )

        # 统一生成 Slice ID (1-based)
        for idx, s in enumerate(slices):
            s["slice_id"] = idx + 1

        return {"total_duration": duration, "slices": slices}
