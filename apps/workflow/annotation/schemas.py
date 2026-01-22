from datetime import datetime
from typing import Any, Dict, List, Optional

from django.db import models
from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel, Field

from apps.common.schemas.dataset.enums import DataOrigin as CoreDataOrigin
from apps.common.schemas.dataset.enums import HighlightMood as CoreHighlightMood
from apps.common.schemas.dataset.enums import HighlightType as CoreHighlightType
from apps.common.schemas.dataset.enums import SceneType as CoreSceneType

# =============================================================================
# 1. 核心枚举 (Core Enums) - 对齐上游 & i18n
# =============================================================================


class SceneType(models.TextChoices):
    """
    [V5.4 修正] 场景类型
    严格对齐 Cloud 端 ScenePreAnnotator 的 Enum 定义
    """

    DIALOGUE = CoreSceneType.DIALOGUE.value, _("对话场")
    ACTION = CoreSceneType.ACTION.value, _("动作场")
    MONTAGE = CoreSceneType.MONTAGE.value, _("蒙太奇")
    ESTABLISHING = CoreSceneType.ESTABLISHING.value, _("建立场")
    EMOTIONAL = CoreSceneType.EMOTIONAL.value, _("情绪场")
    UNKNOWN = CoreSceneType.UNKNOWN.value, _("未知")


class HighlightType(models.TextChoices):
    """[高光类型]"""

    ACTION = CoreHighlightType.ACTION.value, _("动作片段")
    EMOTIONAL = CoreHighlightType.EMOTIONAL.value, _("情感片段")
    DIALOGUE = CoreHighlightType.DIALOGUE.value, _("对话片段")
    SUSPENSE = CoreHighlightType.SUSPENSE.value, _("悬念片段")
    INFORMATION = CoreHighlightType.INFORMATION.value, _("信息片段")
    HUMOR = CoreHighlightType.HUMOR.value, _("幽默片段")
    OTHER = CoreHighlightType.OTHER.value, _("其他")


class HighlightMood(models.TextChoices):
    """[高光情绪]"""

    EXCITING = CoreHighlightMood.EXCITING.value, _("燃")
    SATISFYING = CoreHighlightMood.SATISFYING.value, _("爽")
    HEART_WRENCHING = CoreHighlightMood.HEART_WRENCHING.value, _("虐")
    SWEET = CoreHighlightMood.SWEET.value, _("甜")
    HILARIOUS = CoreHighlightMood.HILARIOUS.value, _("爆笑")
    TERRIFYING = CoreHighlightMood.TERRIFYING.value, _("恐怖")
    HEALING = CoreHighlightMood.HEALING.value, _("治愈")
    TOUCHING = CoreHighlightMood.TOUCHING.value, _("感动")
    TENSE = CoreHighlightMood.TENSE.value, _("紧张")


class DataOrigin(models.TextChoices):
    """[数据来源]"""

    HUMAN = CoreDataOrigin.HUMAN.value, _("人工")
    AI_ASR = CoreDataOrigin.AI_ASR.value, _("AI语音识别")
    AI_LLM = CoreDataOrigin.AI_LLM.value, _("AI大模型")
    AI_CV = CoreDataOrigin.AI_CV.value, _("AI视觉算法")
    AI_OCR = CoreDataOrigin.AI_OCR.value, _("AI文字识别")


# ==========================================
# 2. 上下文组件 (Context Components)
# ==========================================
class AiMetadata(BaseModel):
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    model_version: Optional[str] = None


class ItemContext(BaseModel):
    """
    [原子上下文]
    每个数据块的工程属性，与业务内容隔离。
    """

    id: str = Field(..., description="UUID")
    is_verified: bool = Field(default=False)
    origin: DataOrigin = Field(default=DataOrigin.HUMAN)
    ai_meta: Optional[AiMetadata] = None


# ==========================================
# 3. 业务实体 (Business Content)
# ==========================================
class DialogueContent(BaseModel):
    text: str
    speaker: str = "Unknown"
    original_text: Optional[str] = None


class CaptionContent(BaseModel):
    content: str
    category: Optional[str] = None


class HighlightContent(BaseModel):
    type: HighlightType = Field(default=HighlightType.OTHER)
    mood: Optional[HighlightMood] = None
    description: Optional[str] = None


class SceneContent(BaseModel):
    """
    [V5.4 升级] 场景业务载体 - 严格对齐 Cloud Schema
    """

    # 1. 核心叙事 (Identity)
    # [核心修正] 透传 narrative_action，它是场景的核心定义
    narrative_action: str = Field(..., description="叙事动作/核心事件")

    # Label 是 UI 显示用的短标题，默认由 Parser 从 narrative_action 截取或填充
    label: str = Field(..., description="显示标题")

    # 2. 基础属性
    location: Optional[str] = Field(None, description="主要地点")

    # [核心修正] 使用新定义的 SceneType，并设置默认值为 UNKNOWN (解决 AttributeError)
    scene_type: Optional[SceneType] = Field(default=SceneType.UNKNOWN, description="功能类型")

    # 3. 视觉与情绪
    # [核心修正] 更名为 visual_mood_tags，移除旧的 mood 字段
    visual_mood_tags: List[str] = Field(default_factory=list, description="视觉氛围标签")

    # 4. 导演/剪辑逻辑
    camera_logic: Optional[str] = Field(None, description="运镜/剪辑逻辑 (e.g., Static, Fast cuts)")
    reason: Optional[str] = Field(None, description="AI 分组/切分的理由")
    character_dynamics: Optional[str] = Field(None, description="角色张力/关系")

    # 5. 人工备注
    description: str = Field("", description="人工备注 (Manual Notes)")
    keyframe_url: Optional[str] = None


# ==========================================
# 4 轨道对象 (Track Items)
# ==========================================
class DialogueItem(BaseModel):
    start: float
    end: float
    content: DialogueContent
    context: ItemContext


class CaptionItem(BaseModel):
    start: float
    end: float
    content: CaptionContent
    context: ItemContext


class HighlightItem(BaseModel):
    start: float
    end: float
    content: HighlightContent
    context: ItemContext


class SceneItem(BaseModel):
    start: float
    end: float
    content: SceneContent
    context: ItemContext


# ==========================================
# 5. 工程过程模型 (Engineering Models)
# 生产侧：Workbench 读写 / Edge 存储
# ==========================================


class MediaAnnotation(BaseModel):
    """
    [原子生产单元]
    对应单个 Media 的全量工程文件 (l1_output_file)。
    """

    media_id: str
    file_name: str
    source_path: str
    sequence_number: int
    waveform_data: Optional[List[float]] = None
    character_list: List[str] = Field(default_factory=list, description="全剧角色列表(辅助数据)")

    scenes: List[SceneItem] = []
    dialogues: List[DialogueItem] = []
    captions: List[CaptionItem] = []
    highlights: List[HighlightItem] = []

    duration: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.now)
    version: str = "2.1"  # 升级版本号

    def get_clean_business_data(self) -> Dict[str, Any]:
        """
        [核心方法] 提取纯净业务数据 (去除 Context)
        """

        def clean_list(items: List[Any]) -> List[Dict[str, Any]]:
            result = []
            for item in items:
                base = {"start": item.start, "end": item.end}
                content_dict = item.content.model_dump(exclude_none=True)
                result.append({**base, **content_dict})
            return result

        return {
            "scenes": clean_list(self.scenes),
            "dialogues": clean_list(self.dialogues),
            "captions": clean_list(self.captions),
            "highlights": clean_list(self.highlights),
        }


class ProjectAnnotation(BaseModel):
    """
    [项目生产集合]
    """

    project_id: str
    project_name: str
    character_list: List[str] = Field(default_factory=list)
    annotations: Dict[str, MediaAnnotation] = {}


# ==========================================
# 6. 下游消费模型 (Consumer Models)
# ==========================================


class Chapter(BaseModel):
    """
    [章节] (Consumer Unit)
    """

    id: str = Field(..., description="章节ID (MediaID)")
    sequence_number: int = Field(..., description="叙事顺序")
    name: str = Field(..., description="章节名称")
    source_file: str = Field(..., description="关联视频路径")
    duration: float

    scenes: List[Dict[str, Any]]
    dialogues: List[Dict[str, Any]]
    captions: List[Dict[str, Any]]
    highlights: List[Dict[str, Any]]


class Blueprint(BaseModel):
    """
    [蓝图] (Delivery Artifact)
    """

    project_id: str
    asset_id: str
    project_name: str
    global_character_list: List[str] = Field(default_factory=list)
    chapters: Dict[str, Chapter] = {}
