# 文件路径: apps/refinery/services/context.py

import logging
import shutil
from pathlib import Path
from typing import Dict, List

from django.conf import settings
from django.db import transaction

from ..models import Material

logger = logging.getLogger(__name__)


class RefineryContext:
    def __init__(self, material_id: str):
        self.material_id = material_id
        self.material = None
        self._work_dir_path = None

    def __enter__(self):
        self.transaction = transaction.atomic()
        self.transaction.__enter__()
        try:
            self.material = Material.objects.select_for_update().get(id=self.material_id)
            return self
        except Exception as e:
            self.transaction.__exit__(None, None, None)
            raise e

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._work_dir_path and self._work_dir_path.exists():
            shutil.rmtree(self._work_dir_path)
        self.transaction.__exit__(exc_type, exc_val, exc_tb)

    # --- 1. 物理空间定义 (Path Factory) ---

    @property
    def work_dir(self) -> Path:
        """临时工程目录"""
        if not self._work_dir_path:
            self._work_dir_path = Path(settings.MEDIA_ROOT) / "temp_refinery" / str(self.material_id)
            self._work_dir_path.mkdir(parents=True, exist_ok=True)
        return self._work_dir_path

    @property
    def media_dir(self) -> Path:
        """正式产出基准目录: media_root/refinery/"""
        path = Path(settings.MEDIA_ROOT) / "refinery"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # --- 2. 为Service准备数据，并完成输入前的校验 ---

    @property
    def source_video_path(self) -> Path:
        """源视频绝对路径：用于 Transcode 阶段"""
        try:
            path = Path(self.material.media.source_video.path)
            if not path.exists():
                raise FileNotFoundError(f"Source video physical file missing: {path}")
            return path
        except Exception as e:
            raise RuntimeError(f"Context read source_video_path error: {str(e)}")

    @property
    def proxy_video_path(self) -> Path:
        """基准代理视频绝对路径：用于所有后续精炼阶段"""
        if not self.material.proxy_video:
            raise AttributeError(
                f"Material {self.material_id} 'proxy_video' field is empty. Ensure Transcode stage is finished."
            )

        abs_path = self.media_dir / self.material.proxy_video
        if not abs_path.exists():
            raise FileNotFoundError(f"Proxy video physical file missing: {abs_path}")

        return abs_path

    @property
    def source_subtitle_content(self) -> str:
        """读取源媒体字幕内容"""
        sub_file = self.material.media.source_subtitle
        if not sub_file:
            return ""  # 允许字幕为空，但这取决于业务逻辑（Task层可据此判断是否跳过分析）

        try:
            # 这里的 sub_file 是 Django 的 FieldFile，自带 open 方法
            with sub_file.open("r") as f:
                content = f.read()
                # 兼容处理字节流与字符串
                return content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else content
        except Exception as e:
            raise IOError(f"Failed to read source subtitle content: {str(e)}")

    @property
    def duration(self) -> float:
        """获取视频基准时长（必须已由 Probe 产出）"""
        duration = self.material.duration
        if duration is None or duration <= 0:
            raise ValueError(
                f"Material {self.material_id} 'duration' is invalid ({duration}). Ensure Probe stage is finished."
            )
        return float(duration)

    @property
    def dialogue_track(self) -> list:
        """获取结构化对白清单（必须已由 AnalyzeText 产出）"""
        track = self.material.dialogue_track
        if track is None:
            raise ValueError(
                f"Material {self.material_id} 'dialogue_track' is None. Ensure Text Analysis stage is finished."
            )
        return track

    @property
    def visual_slices(self) -> list:
        """获取视觉切片清单（用于 Frame Extraction）"""
        slices = self.material.visual_slices
        if not slices:
            raise ValueError(f"Material {self.material_id} 'visual_slices' is empty. Ensure Slicing stage is finished.")
        return slices

    # --- 3. 业务提交 (Outputs) ---

    def commit_transcode_status(self, relative_proxy_path: str):
        """记录相对于 media_dir 的路径"""
        self.material.proxy_video = relative_proxy_path.replace("\\", "/")
        if self.material.status == self.material.Status.TRANSCODING:
            self.material.finish_current_task()
        self.material.save(update_fields=["proxy_video", "status", "modified"])
        logger.info(f"Context: Transcode path committed -> {relative_proxy_path}")

    def commit_probe_results(self, tech_meta, duration, waveform):
        self.material.tech_meta = tech_meta
        self.material.duration = duration
        if waveform:
            self.material.waveform_data = {"version": 1, "data": waveform}
        if self.material.status == self.material.Status.PROBING:
            self.material.finish_current_task()
        self.material.save(update_fields=["tech_meta", "duration", "waveform_data", "status", "modified"])
        logger.info(f"Context: Probe results committed (duration: {duration})")

    def commit_analysis_results(self, dialogue_track: list):
        self.material.dialogue_track = dialogue_track
        if self.material.status == self.material.Status.ANALYZING_TEXT:
            self.material.finish_current_task()
        self.material.save(update_fields=["dialogue_track", "status", "modified"])
        logger.info(f"Context: Dialogue track committed ({len(dialogue_track)} entries)")

    def commit_hls_status(self, relative_index_path: str):
        self.material.hls_playlist = relative_index_path.replace("\\", "/")
        if self.material.status == self.material.Status.HLS_FRAGMENTING:
            self.material.finish_current_task()
        self.material.save(update_fields=["hls_playlist", "status", "modified"])
        logger.info(f"Context: HLS playlist committed -> {relative_index_path}")

    def commit_slicing_results(self, visual_slices: List[Dict]):
        """注入视觉切片清单"""
        self.material.visual_slices = visual_slices

        if self.material.status == self.material.Status.SLICING:
            self.material.finish_current_task()

        self.material.save(update_fields=["visual_slices", "status", "modified"])
        logger.info(f"Context: Committed {len(visual_slices)} visual slices for {self.material_id}")

    def commit_extracted_frames(self, updated_slices: List[Dict]):
        """持久化带图片路径的切片数据"""
        self.material.visual_slices = updated_slices

        if self.material.status == self.material.Status.FRAME_EXTRACTING:
            self.material.finish_current_task()

        self.material.save(update_fields=["visual_slices", "status", "modified"])
        logger.info(f"Context: All frames committed for {self.material_id}")
