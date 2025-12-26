# apps/workflow/scene_orchestration/services/service.py

import logging
import uuid
from typing import Any, Dict, List

from apps.workflow.models import AnnotationProject, TranscodingJob
from apps.workflow.scene_orchestration.schemas import (
    EdgeRelation,
    LogicTimeline,
    LogicType,
    NodeType,
    OrchestrationEdge,
    OrchestrationGraph,
    OrchestrationNodeState,
    SceneNode,
)

logger = logging.getLogger(__name__)


class OrchestrationService:
    @classmethod
    def get_orchestration_source_data(cls, project: AnnotationProject) -> Dict[str, Any]:
        """
        [Query] 聚合全剧场景并构建逻辑编排图谱 (V3.1 Implementation)
        """
        # 1. 准备数据源
        jobs = (
            project.jobs.filter(status__in=["COMPLETED", "PROCESSING"], annotation_file__isnull=False)
            .exclude(annotation_file="")
            .select_related("media")
            .order_by("media__sequence_number")
        )

        all_scenes: List[SceneNode] = []
        global_index = 0

        # [V3.1] 预先生成一个默认的物理主轴 ID
        # 如果是冷启动，所有节点默认都在这条主轴上
        default_timeline_id = str(uuid.uuid4())

        # 2. 遍历 Job 加载 SceneNode
        for job in jobs:
            # 获取流地址 (逻辑保持不变)
            media = job.media
            stream_url = ""
            try:
                transcoding_job = (
                    TranscodingJob.objects.filter(media=media, status="COMPLETED").order_by("-modified").first()
                )
                if transcoding_job and transcoding_job.output_url:
                    stream_url = transcoding_job.output_url
                else:
                    stream_url = media.get_best_playback_url()
            except Exception:
                pass

            try:
                media_anno = cls.load_annotation(job)

                for i, scene_item in enumerate(media_anno.scenes):
                    content = scene_item.content

                    # [V3.1] 使用源文件 UUID
                    node_id = scene_item.context.id

                    # [V3.1] 构造前端契约 SceneNode
                    # 必须赋予 timeline_id 和 node_type
                    scene_node = SceneNode(
                        id=node_id,
                        index=global_index,
                        label=content.label or f"SC-{global_index + 1}",
                        narrative_action=content.narrative_action or "无描述",
                        location=content.location or "Unknown",
                        scene_type=content.scene_type or "unknown",
                        visual_mood_tags=content.visual_mood_tags,
                        # New Logic Fields
                        node_type=NodeType.EVENT,
                        timeline_id=default_timeline_id,  # 默认归属主轴
                        needsResequence=False,
                        startTime=scene_item.start,
                        endTime=scene_item.end,
                        duration=scene_item.end - scene_item.start,
                        streamUrl=stream_url,
                    )
                    all_scenes.append(scene_node)
                    global_index += 1
            except Exception as e:
                logger.error(f"Failed to process job {job.id}: {e}")
                continue

        # 3. 准备逻辑图谱 (OrchestrationGraph)
        graph_data = project.orchestration_graph
        final_graph = {}

        # 检查是否存在有效的 V3 图谱 (简单的版本检查或字段检查)
        has_valid_graph = (
            graph_data
            and isinstance(graph_data, dict)
            and graph_data.get("version") == "3.1"
            and graph_data.get("timelines")  # V3 必须有 timelines
        )

        if has_valid_graph:
            # Case A: 热启动 - 使用存档
            logger.info(f"Loaded V3.1 graph for Project {project.id}")
            final_graph = graph_data

            # [Sync] 我们需要用存档中的状态(timeline_id, node_type)去覆盖 raw scenes 里的默认值
            # 否则 Sidebar 里的状态和画布上的状态不一致
            saved_nodes_map = {n["id"]: n for n in graph_data.get("nodes", [])}

            for sc in all_scenes:
                if sc.id in saved_nodes_map:
                    saved_state = saved_nodes_map[sc.id]
                    sc.node_type = saved_state.get("node_type", NodeType.EVENT)
                    sc.timeline_id = saved_state.get("timeline_id", default_timeline_id)

        else:
            # Case B: 冷启动 / 强制升级 - 生成默认逻辑链
            logger.info(f"Generating default V3.1 LogicTimeline for {len(all_scenes)} scenes.")

            # 1. 创建默认主轴
            main_timeline = LogicTimeline(
                id=default_timeline_id, name="主时间轴 (Physical Main)", type=LogicType.PHYSICAL_MAIN, color="#1890ff"
            )

            default_edges = []
            default_nodes = []

            # 2. 按物理顺序构建 CONTINUE 连线
            sorted_scenes = sorted(all_scenes, key=lambda x: x.index)

            for i in range(len(sorted_scenes) - 1):
                source = sorted_scenes[i]
                target = sorted_scenes[i + 1]

                edge = OrchestrationEdge(
                    source=source.id, target=target.id, relation=EdgeRelation.CONTINUE  # [V3.1] 使用 CONTINUE
                )
                default_edges.append(edge.model_dump())

            # 3. 构建节点状态快照
            for sc in sorted_scenes:
                node_state = OrchestrationNodeState(id=sc.id, node_type=NodeType.EVENT, timeline_id=default_timeline_id)
                default_nodes.append(node_state.model_dump())

            final_graph = OrchestrationGraph(
                timelines=[main_timeline], nodes=default_nodes, edges=default_edges
            ).model_dump()

        return {"scenes": [s.model_dump() for s in all_scenes], "graph": final_graph}

    @classmethod
    def save_orchestration_graph(cls, project: AnnotationProject, graph_payload: Dict) -> None:
        """
        [Command] 保存编排结果
        """
        # 这里可以加一层 Schema 校验，确保前端传回来的是合法的 V3 结构
        try:
            # 验证 payload 是否符合 OrchestrationGraph 定义
            graph_obj = OrchestrationGraph(**graph_payload)
            project.orchestration_graph = graph_obj.model_dump()
            project.save(update_fields=["orchestration_graph"])
        except Exception as e:
            logger.error(f"Invalid graph payload: {e}")
            raise ValueError(f"Graph validation failed: {e}")
