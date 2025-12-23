from datetime import datetime
from typing import Any, Dict, List, Optional

from django.db import models
from django.utils.translation import gettext_lazy as _
from pydantic import BaseModel, Field

# =============================================================================
# 1. 核心枚举 (Core Enums) - i18n 增强版
# =============================================================================


class SceneMood(models.TextChoices):
    """
    [场景氛围]
    Value (存储值) = "Calm"
    Label (显示名) = "平静" (支持 i18n)
    """

    CALM = "Calm", _("平静")
    TENSE = "Tense", _("紧张")
    ROMANTIC = "Romantic", _("浪漫")
    JOYFUL = "Joyful", _("喜悦")
    SAD = "Sad", _("悲伤")
    MYSTERIOUS = "Mysterious", _("悬疑/神秘")
    ANGRY = "Angry", _("愤怒")
    CONFRONTATIONAL = "Confrontational", _("冲突")
    FEARFUL = "Fearful", _("恐惧")
    OPPRESSIVE = "Oppressive", _("压抑")
    EERIE = "Eerie", _("诡异")
    WARM = "Warm", _("温馨")


class SceneType(models.TextChoices):
    """[场景类型]"""

    DIALOGUE_HEAVY = "Dialogue_Heavy", _("对话驱动")
    ACTION_DRIVEN = "Action_Driven", _("动作驱动")
    INTERNAL_MONOLOGUE = "Internal_Monologue", _("内心独白")
    VISUAL_STORYTELLING = "Visual_Storytelling", _("视觉叙事")
    TRANSITION = "Transition", _("过场")
    ESTABLISHING = "Establishing", _("铺垫/空镜")


class HighlightType(models.TextChoices):
    """[高光类型]"""

    ACTION = "Action", _("动作片段")
    EMOTIONAL = "Emotional", _("情感片段")
    DIALOGUE = "Dialogue", _("对话片段")
    SUSPENSE = "Suspense", _("悬念片段")
    INFORMATION = "Information", _("信息片段")
    HUMOR = "Humor", _("幽默片段")
    OTHER = "Other", _("其他")


class HighlightMood(models.TextChoices):
    """[高光情绪]"""

    EXCITING = "Exciting", _("燃")
    SATISFYING = "Satisfying", _("爽")
    HEART_WRENCHING = "Heart-wrenching", _("虐")
    SWEET = "Sweet", _("甜")
    HILARIOUS = "Hilarious", _("爆笑")
    TERRIFYING = "Terrifying", _("恐怖")
    HEALING = "Healing", _("治愈")
    TOUCHING = "Touching", _("感动")
    TENSE = "Tense", _("紧张")


class DataOrigin(models.TextChoices):
    """[数据来源]"""

    HUMAN = "human", _("人工")
    AI_ASR = "ai_asr", _("AI语音识别")
    AI_LLM = "ai_llm", _("AI大模型")
    AI_CV = "ai_cv", _("AI视觉算法")
    AI_OCR = "ai_ocr", _("AI文字识别")


# ==========================================
# 2. 上下文组件 (Context Components) - 保持不变
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
# 3. 业务实体 (Business Content) - 保持不变
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
    [V5.3 升级] 场景业务载体
    完全对齐 Cloud 端 ScenePreAnnotatorResult 的丰富度
    """

    # 1. 核心标识
    label: str = Field(..., description="场景标题/简述，对应 narrative_action")

    # 2. 基础属性
    location: Optional[str] = Field(None, description="主要地点")
    scene_type: Optional[SceneType] = Field(None, description="功能类型")

    # 3. [新增] 导演/剪辑逻辑
    camera_logic: Optional[str] = Field(None, description="运镜/剪辑逻辑 (e.g., Static, Fast cuts)")
    reason: Optional[str] = Field(None, description="AI 分组/切分的理由 (Segmentation Reason)")

    # 4. [新增] 视觉与情绪
    # 升级：不再只存单个 mood，而是存储完整的标签列表
    tags: List[str] = Field(default_factory=list, description="视觉氛围标签 (visual_mood_tags)")
    # 兼容：仍保留 mood 字段作为 '主导情绪'，供旧版 UI 兼容显示
    mood: Optional[SceneMood] = None

    # 5. 角色关系
    character_dynamics: Optional[str] = Field(None, description="角色张力/关系")

    # 6. 其他
    description: str = Field("", description="补充描述")
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

    # 媒资关联
    media_id: str
    file_name: str
    source_path: str
    sequence_number: int
    waveform_url: Optional[str] = None

    # 核心数据 (四条轨道)
    scenes: List[SceneItem] = []
    dialogues: List[DialogueItem] = []
    captions: List[CaptionItem] = []
    highlights: List[HighlightItem] = []

    # 元数据
    duration: float = 0.0  # 物理文件时长
    updated_at: datetime = Field(default_factory=datetime.now)
    version: str = "2.0"  # Schema 版本

    def get_clean_business_data(self) -> Dict[str, Any]:
        """
        [核心方法] 提取纯净业务数据 (去除 Context)
        供 Blueprint 生成使用
        """

        def clean_list(items: List[Any]) -> List[Dict[str, Any]]:
            result = []
            for item in items:
                # 1. 提取时间轴
                base = {"start": item.start, "end": item.end}
                # 2. 提取内容 (展平)
                # exclude_none=True 会过滤掉没填的字段
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
    对应整个 Project 的全量工程状态。
    这是 Edge 内部视角的“项目全貌”。
    """

    project_id: str
    project_name: str

    # 全局角色表 (含工程状态，如是否人工确认过该角色存在)
    character_list: List[str] = Field(default_factory=list)

    # 包含所有原子单元
    annotations: Dict[str, MediaAnnotation] = {}


# ==========================================
# 6. 下游消费模型 (Consumer Models)
# 消费侧：VSS-Cloud 接收 / Inference 输入
# ==========================================


class Chapter(BaseModel):
    """
    [章节] (Consumer Unit)
    对应 MediaAnnotation 的清洗版。
    只包含业务内容 (start, end, content)，剔除了 context。
    """

    id: str = Field(..., description="章节ID (MediaID)")
    sequence_number: int = Field(..., description="叙事顺序，用于 VSS Cloud 排序和逻辑处理")
    name: str = Field(..., description="章节名称")
    source_file: str = Field(..., description="关联视频路径")
    duration: float

    # 注意：这里的结构被扁平化了，直接暴露 Content 字段，或者复用 Content 对象
    # 为了下游使用方便，通常我们会把 Content 里的字段展开，或者保留 Content 结构
    # 这里为了保持与旧版 Blueprint 的“业务纯净度”，我们定义为：
    scenes: List[Dict[str, Any]]  # 这里的 Dict 是清洗后的 Scene (start, end, ...content fields)
    dialogues: List[Dict[str, Any]]
    captions: List[Dict[str, Any]]
    highlights: List[Dict[str, Any]]


class Blueprint(BaseModel):
    """
    [蓝图] (Delivery Artifact)
    对应 ProjectAnnotation 的清洗版。
    最终发给 Cloud 的 JSON。
    """

    project_id: str
    asset_id: str
    project_name: str

    # 纯净的角色列表
    global_character_list: List[str] = Field(default_factory=list)

    # 章节集合
    chapters: Dict[str, Chapter] = {}
