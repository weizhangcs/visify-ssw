# apps/refinery/services/scheduler.py
import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from apps.refinery.models import Material

logger = logging.getLogger(__name__)


@dataclass
class RefineryRule:
    slug: str  # 唯一标识 (用于 API 和指标 Key)
    name: str  # UI 友好名称
    target_status: str  # 对应的 FSM 状态
    is_satisfied: Callable[[Material], bool]  # 准入判定：True 表示数据缺失，需执行
    task_name: str  # 绑定的 Celery 任务名


class RefineryScheduler:
    # 配置式规则描述：定义严格的线性精炼顺序
    RULES: List[RefineryRule] = [
        RefineryRule(
            "transcode", "标准化转码", Material.Status.TRANSCODING, lambda m: not m.proxy_video, "refinery_transcode_task"
        ),
        RefineryRule(
            "probe",
            "元数据探测",
            Material.Status.PROBING,
            lambda m: m.duration <= 0 or not m.tech_meta,
            "refinery_probe_task",
        ),
        RefineryRule(
            "analyze_text",
            "文本清洗",
            Material.Status.ANALYZING_TEXT,
            lambda m: bool(m.media.source_subtitle) and not m.dialogue_track,
            "refinery_analyze_text_task",
        ),
        RefineryRule(
            "character_recognition",
            "角色识别",
            Material.Status.CHARACTER_RECOGNIZING,
            lambda m: bool(m.media.source_subtitle) and m.dialogue_track,
            "refinery_character_recognition_task",
        ),
        RefineryRule(
            "hls",
            "HLS切片",
            Material.Status.HLS_FRAGMENTING,
            lambda m: bool(m.proxy_video) and not m.hls_playlist,
            "refinery_hls_task",
        ),
        RefineryRule(
            "slicing",
            "视觉切片",
            Material.Status.SLICING,
            lambda m: bool(m.proxy_video) and bool(m.dialogue_track) and not m.visual_slices,
            "refinery_slicing_task",
        ),
        RefineryRule(
            "frame_extract",
            "抽帧提取",
            Material.Status.FRAME_EXTRACTING,
            lambda m: bool(m.visual_slices) and not any(s.get("frames") for s in m.visual_slices),
            "refinery_frame_extract_task",
        ),
        RefineryRule(
            "sync",
            "云端同步",
            Material.Status.SYNCING,
            lambda m: bool(m.visual_slices)
            and any(s.get("frames") and not s["frames"][0]["path"].startswith("gs://") for s in m.visual_slices),
            "refinery_sync_task",
        ),
    ]

    @classmethod
    def get_pipeline_state(cls, material: Material) -> List[Dict]:
        """[白盒化核心] 为 View 提供全量过程数据"""
        state_list = []
        metrics = material.pipeline_metrics or {}
        found_breakpoint = False

        for rule in cls.RULES:
            is_done = not rule.is_satisfied(material)
            metric = metrics.get(rule.slug, {})

            step_info = {
                "slug": rule.slug,
                "name": rule.name,
                "is_done": is_done,
                "duration": metric.get("duration"),
                "finished_at": metric.get("finished_at"),
                "is_current": False,
                "has_error": False,
                "error_log": "",
            }

            # 判定当前执行点或断点
            if not is_done and not found_breakpoint:
                step_info["is_current"] = True
                found_breakpoint = True
                if material.status == Material.Status.FAILED:
                    step_info["has_error"] = True
                    step_info["error_log"] = material.error_log

            state_list.append(step_info)
        return state_list

    @classmethod
    def record_and_schedule(cls, material_id: str, slug: str, duration: float):
        """[回流入口] 记录指标并驱动下一步"""
        material = Material.objects.get(id=material_id)
        metrics = material.pipeline_metrics or {}
        metrics[slug] = {"duration": duration, "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        material.pipeline_metrics = metrics
        material.save(update_fields=["pipeline_metrics"])

        # 触发自动决策
        cls.schedule(material_id)

    @classmethod
    def schedule(cls, material_id: str, start_from_slug: Optional[str] = None):
        """线性决策引擎：支持断点续传与手动重入"""
        material = Material.objects.get(id=material_id)

        target_rule = None
        if start_from_slug:
            # 手动定点重试
            target_rule = next((r for r in cls.RULES if r.slug == start_from_slug), None)
        else:
            # 自动寻找第一个数据缺失点
            target_rule = next((r for r in cls.RULES if r.is_satisfied(material)), None)

        if target_rule:
            cls._dispatch(material, target_rule)
        else:
            if material.status != Material.Status.READY:
                material.mark_ready()
                material.save(update_fields=["status", "modified"])

    @classmethod
    def _dispatch(cls, material, rule):
        """执行状态流转并异步分发"""
        transition_method = f"start_{rule.target_status.lower()}"
        if hasattr(material, transition_method):
            getattr(material, transition_method)()
            material.save(update_fields=["status", "modified"])

        from .. import tasks

        task_func = getattr(tasks, rule.task_name)
        task_func.delay(str(material.id))
