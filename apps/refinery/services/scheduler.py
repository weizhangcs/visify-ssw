# 文件路径: apps/refinery/services/scheduler.py

from dataclasses import dataclass
from typing import Callable

from apps.refinery.models import Material


@dataclass
class RefineryRule:
    name: str
    target_status: str
    # 核心：基于数据的准入判定
    is_satisfied: Callable[[Material], bool]
    # 对应的原子任务
    task_name: str


class RefineryScheduler:
    """
    [精炼决策引擎] 基于 PENDING 状态的回流决策机制。
    """

    # 声明式规则集：定义管线中每个步点的“数据缺失条件”
    # 只要满足 is_satisfied (即数据缺失)，就进入该 target_status 并执行任务
    RULES = [
        # RefineryRule(
        # name="Metadata Probing",
        # target_status=Material.Status.PROBING,
        # 检查 dict 是否为空
        # is_satisfied=lambda m: not m.tech_meta,
        # task_name="refinery_probe_task",
        # ),
        # 2. 文本清洗 (新增: 依赖源字幕文件，产出 dialogue_track)
        # RefineryRule(
        # name="Text Analyzing",
        # target_status=Material.Status.ANALYZING_TEXT,
        # 准入条件：源媒体有字幕文件 且 物料中还没有结构化对白数据
        # is_satisfied=lambda m: bool(m.media.source_subtitle) and not m.dialogue_track,
        # task_name="refinery_analyze_text_task",
        # ),
    ]

    @classmethod
    def schedule(cls, material_id: str):
        from apps.refinery.models import Material

        material = Material.objects.get(id=material_id)

        # 核心约束：只有在 PENDING 状态下才进行管线决策 : TODO: 临时改成READY 免得单元测试被Scheduler干扰
        if material.status != Material.Status.READY:
            return

        # 遍历规则引擎，寻找第一个满足（数据缺失）的规则
        for rule in cls.RULES:
            if rule.is_satisfied(material):
                cls._dispatch(material, rule)
                return

        # 终点：如果没有任何规则被命中（代表数据全部就绪），则标记 READY
        if material.status == Material.Status.PENDING:
            material.mark_ready()
            material.save(update_fields=["status", "modified"])

    @classmethod
    def _dispatch(cls, material, rule: RefineryRule):
        """执行 FSM 跳转并分发 Celery 任务"""
        # 动态调用模型的 start_xxx 方法
        transition_method = f"start_{rule.target_status.lower()}"
        if hasattr(material, transition_method):
            getattr(material, transition_method)()
            material.save(update_fields=["status", "modified"])

            # 派发任务
            from .. import tasks

            task_func = getattr(tasks, rule.task_name)
            task_func.delay(str(material.id))
