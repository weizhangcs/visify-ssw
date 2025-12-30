from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ExecMode(str, Enum):
    SYNC = "SYNC"
    ASYNC = "ASYNC"


class ResourceClass(str, Enum):
    GENERAL = "GENERAL"
    NETWORK = "NETWORK"
    IO = "IO"
    COMPUTING = "COMPUTING"
    AI = "AI"
    TRANSFER = "TRANSFER"


class FlowObligation(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class FlowType(str, Enum):
    START = "START"
    IN_THE_MIDDLE = "IN_THE_MIDDLE"
    END = "END"


class AtomUnitSchema(BaseModel):
    """原子算子能力的完整定义"""

    name: str
    slug: str
    description: Optional[str] = ""
    exec_mode: ExecMode
    res_class: ResourceClass


class FlowRuleItemSchema(BaseModel):
    """rules_config 数组中的每一项"""

    seq: int = Field(..., description="流程内的绝对索引编号")
    unit_slug: str = Field(..., description="关联的 BaseAtomUnit 的 slug")
    name: str = Field(..., description="显示给 UI 的任务名称")
    description: Optional[str] = ""
    flow_type: FlowType = Field(default=FlowType.IN_THE_MIDDLE)
    obligation: FlowObligation = Field(default=FlowObligation.REQUIRED)
    dependence: List[int] = Field(default_factory=list, description="依赖的前置 seq 列表")
    worker_queue: str = Field(default="general", description="指定的 Celery 队列")


class AtomflowRuleSchema(BaseModel):
    """完整的规则编排定义"""

    rules: List[FlowRuleItemSchema]
