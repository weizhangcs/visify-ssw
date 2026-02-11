# 向量引擎语义映射表 (Vector Semantic Mapping Table)

本文档详细描述了 `apps.vector` 子系统中，结构化业务数据如何被清洗、转义为自然语言文本（Corpus），以供 Embedding 模型进行向量化。

**核心处理类**: `apps.vector.services.processor.DataProcessorService`
**配置文件路径**: `apps/vector/metadata/*.json`

---

## 1. 对白 (Dialogue)

对白是最基础的语义单元，主要用于搜索特定台词或说话人。

*   **数据源**: `Material.dialogues` (List[SubtitleItem])
*   **索引类型**: `dialogue`
*   **拼接逻辑**: `[角色名][分隔符][台词内容]`

### 映射规则

| 字段 (JSON Field) | 标签 (Label) | 说明 |
| :--- | :--- | :--- |
| `speaker` | (无) | 角色名，若为空则默认为 "Unknown" |
| `content` | (无) | 台词文本内容 |

### 配置 (metadata/dialogue.json)

```json
{
  "zh": { "separator": "：" },
  "en": { "separator": ": " }
}
```

### 示例 (Example)

**输入 (Input):**
```json
{
  "speaker": "钢铁侠",
  "content": "也就是说是你把我们带到这里来的？"
}
```

**输出 (Processed Text):**
```text
钢铁侠：也就是说是你把我们带到这里来的？
```

---

## 2. 场景 (Scene)

场景是宏观叙事单元，聚合了剧情、地点和氛围信息。

*   **数据源**: `Material.scenes` -> `content` (SceneContent)
*   **索引类型**: `scene`
*   **拼接逻辑**: `[标签][分隔符][内容]；[标签][分隔符][内容]...`

### 映射规则

| 字段 (JSON Field) | 默认标签 (zh) | 说明 |
| :--- | :--- | :--- |
| `content.narrative_action` | **剧情** | 核心叙事动作 |
| `content.location` | **地点** | 场景发生地点 |
| `content.visual_mood_tags` | **氛围** | 视觉/情绪标签列表 (用 `、` 连接) |

### 配置 (metadata/scene.json)

*   **Separator**: `；` (中文分号)

### 示例 (Example)

**输入 (Input):**
```json
{
  "content": {
    "narrative_action": "主角在雨中奔跑，试图追赶离去的车辆",
    "location": "繁华的十字路口",
    "visual_mood_tags": ["紧张", "悲伤", "雨夜"]
  }
}
```

**输出 (Processed Text):**
```text
剧情：主角在雨中奔跑，试图追赶离去的车辆；地点：繁华的十字路口；氛围：紧张、悲伤、雨夜
```

---

## 3. 切片 (Slice)

切片是中观单元，结合了画面描述和剧情摘要。

*   **数据源**: `Material.slices` -> `slice_analysis` (SliceAnalysis)
*   **索引类型**: `slice`
*   **拼接逻辑**: `[标签][分隔符][内容]；...`

### 映射规则

| 字段 (JSON Field) | 默认标签 (zh) | 说明 |
| :--- | :--- | :--- |
| `slice_analysis.visual_summary` | **画面** | 视觉内容的详细描述 |
| `slice_analysis.narrative_summary` | **剧情** | 该片段发生的剧情摘要 |

### 配置 (metadata/slice.json)

*   **Separator**: `；`

### 示例 (Example)

**输入 (Input):**
```json
{
  "slice_analysis": {
    "visual_summary": "特写镜头展示了一只手紧紧握住咖啡杯，蒸汽升腾",
    "narrative_summary": "表现人物内心的焦虑与不安"
  }
}
```

**输出 (Processed Text):**
```text
画面：特写镜头展示了一只手紧紧握住咖啡杯，蒸汽升腾；剧情：表现人物内心的焦虑与不安
```

---

## 4. 关键帧 (Frame)

关键帧是微观视觉单元，包含详细的视觉识别信息。

*   **数据源**: `Material.frames` -> `visual_analysis` (VisualAnalysis)
*   **索引类型**: `frame`
*   **拼接逻辑**: `[标签][分隔符][内容]；...`

### 映射规则

| 字段 (JSON Field) | 默认标签 (zh) | 说明 |
| :--- | :--- | :--- |
| `subject` | **主体** | 画面中的主要对象 |
| `action` | **动作** | 主体的动作 |
| `environment` | **环境** | 物理环境描述 |
| `shot_type` | **景别** | 如：特写、全景 (支持 LabelValue 或 String) |
| `lighting_time` | **光影** | 如：白天、夜晚、逆光 |
| `visual_mood_tags` | **氛围** | 视觉标签列表 |

### 配置 (metadata/frame.json)

*   **Separator**: `；`

### 示例 (Example)

**输入 (Input):**
```json
{
  "visual_analysis": {
    "subject": "一只金毛犬",
    "action": "跳跃接飞盘",
    "environment": "阳光明媚的草地",
    "shot_type": "中景",
    "lighting_time": "正午阳光",
    "visual_mood_tags": ["活力", "快乐"]
  }
}
```

**输出 (Processed Text):**
```text
主体：一只金毛犬；动作：跳跃接飞盘；环境：阳光明媚的草地；景别：中景；光影：正午阳光；氛围：活力、快乐
```

---

## 5. 存储元数据 (Stored Metadata)

为了实现从“语义向量”到“业务数据”的反向查找，我们在构建 FAISS 索引时，会同步存储一份轻量级的元数据列表（Metadata List）。

**统一元数据结构 (Schema):**

| 字段 (Field) | 类型 | 说明 | 取值逻辑 |
| :--- | :--- | :--- | :--- |
| `id` | UUID (str) | 原始数据的唯一标识 | `item.id` |
| `start` | Float | 起始时间 (秒) | 优先取 `start_time`，若无则取 `timestamp` (兼容 Frame) |
| `end` | Float | 结束时间 (秒) | `item.end_time` (Frame 默认为 0) |
| `text_preview` | String | 文本预览 | 截取 `processed_text` 前 100 个字符，用于调试或快速展示 |

**检索机制**:
FAISS 检索返回的是向量在数组中的 **Index (下标)**。系统利用此下标在 Metadata List 中查找对应的字典，从而获取 `id` 和时间戳，最终回溯到数据库中的具体记录。