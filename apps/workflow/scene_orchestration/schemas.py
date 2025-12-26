# apps/workflow/scene_orchestration/schemas.py
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

# ==========================================
# 1. 核心枚举：逻辑分析语汇 (V3.1)
# ==========================================


class NodeType(str, Enum):
    """
    [属性维度] 节点的本体性质
    """

    EVENT = "event"  # [事实] 客观发生的事件
    FUNCTIONAL = "functional"  # [工具] 字幕、黑场、空镜


class EdgeRelation(str, Enum):
    """
    [拓扑维度] 连接的性质 (V3.1)
    """

    CONTINUE = "continue"  # [顺承] 同一逻辑链的自然流动
    FORK = "fork"  # [分叉] 衍生出新的逻辑分支
    MERGE = "merge"  # [汇合] 回归主干
    ATTACH = "attach"  # [挂载] 功能性依附


class LogicType(str, Enum):
    """
    [容器维度] 逻辑链的性质
    """

    PHYSICAL_MAIN = "physical_main"  # 物理主轴
    PHYSICAL_BRANCH = "physical_branch"  # 物理分支
    HYPOTHETICAL = "hypothetical"  # 假想/推演


# ==========================================
# 2. 前端契约：输入 (Frontend Contract - Input)
# ==========================================


class SceneNode(BaseModel):
    """
    [Frontend Input] 场景节点数据结构
    用于编排工作台初始化加载。
    Service 会将物理素材封装成这个对象发送给前端。
    """

    # --- 基础身份 ---
    id: str = Field(..., description="全局唯一ID (对应 Scene.context.id UUID)")
    index: int = Field(..., description="全局物理顺序索引 (0-based)")
    label: str = Field(..., description="显示标签 (e.g. SC-1)")

    # --- 核心叙事属性 (来自审订数据) ---
    narrative_action: str = Field(..., description="剧情摘要")
    location: str = Field(default="Unknown", description="地点")
    scene_type: str = Field(default="unknown", description="场景类型")
    visual_mood_tags: List[str] = Field(default_factory=list, description="视觉氛围标签")

    # --- 编排状态 (V3.1 初始状态) ---
    # [升级] 不再使用 logicRole，而是预分配 node_type 和 timeline_id
    node_type: NodeType = Field(default=NodeType.EVENT, description="初始节点类型")

    # Service 在生成 Input 时，会预先计算它属于哪条逻辑链 (通常默认为 主链ID)
    timeline_id: str = Field(..., description="初始归属的逻辑链ID")

    needsResequence: bool = Field(default=False, description="是否需要重排 (UI提示用)")

    # --- 媒体信息 ---
    startTime: float = Field(..., description="开始时间 (秒)")
    endTime: float = Field(..., description="结束时间 (秒)")
    duration: float = Field(..., description="时长 (秒)")
    streamUrl: str = Field(..., description="HLS 流地址")


# ==========================================
# 3. 持久化对象：过程与产出 (Persisted Data - Output)
# ==========================================


class LogicTimeline(BaseModel):
    """
    [Container] 逻辑因果链 (泳道)
    """

    id: str
    name: str
    type: LogicType = LogicType.PHYSICAL_MAIN
    description: Optional[str] = None
    color: str = "#1890ff"


class OrchestrationNodeState(BaseModel):
    """
    [State Snapshot] 节点保存时的状态
    """

    id: str  # 对应 SceneNode.id
    node_type: NodeType  # 可能被用户修改 (e.g. 标记为空镜)
    timeline_id: str  # 可能被用户拖拽到其他链


class OrchestrationEdge(BaseModel):
    """
    [Topology] 逻辑连线
    """

    source: str
    target: str
    relation: EdgeRelation  # CONTINUE / FORK / MERGE / ATTACH


class OrchestrationGraph(BaseModel):
    """
    [Output Root] 事实编排图谱 V3.1
    用户点击"保存"时提交的结构
    """

    version: str = "3.1"

    timelines: List[LogicTimeline] = []
    nodes: List[OrchestrationNodeState] = []
    edges: List[OrchestrationEdge] = []
