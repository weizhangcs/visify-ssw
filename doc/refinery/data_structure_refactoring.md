# Refinery 数据结构重构与向量化演进规划

## 1. 核心设计意图

Refinery 将从单纯的“数据预处理流水线”，升级为多模态资产的“矿场”与“银行”。我们将数据划分为 **“语义侧”**（Dialogues, Scenes）和 **“视听物理侧”**（Slices, Keyframes），明确各自的独立价值与消费场景。

### 1.1 Dialogues (实体：文本流)
*   **定位**：人物与信息的基石。
*   **价值**：
    *   **人物画像**：通过向量化对白，回答“主角在什么时候表现出了愤怒？”或“谁是背叛者？”。
    *   **人工修订**：作为 SSOT (Single Source of Truth)，支持 Workbench 人工介入，修订后同步更新向量索引。

### 1.2 Scenes (聚合：叙事面)
*   **定位**：故事线的骨架。
*   **价值**：
    *   **解说生成**：AI 理解“这一段剧情讲了什么”才能生成旁白。Scene 的向量化（Narrative Summary Embedding）是关键。
    *   **粗粒度检索**：支持基于剧情描述（如“激烈的追车戏”）的检索。

### 1.3 Slices (实体：镜头/原子片段) —— *被挖掘的宝藏 A*
*   **定位**：自动化剪辑的素材库。
*   **价值**：
    *   **素材选择器**：AIGC 剪辑的核心。通过 Slice 向量索引（Visual Summary + Tags）瞬间找到对应的 3-5 秒片段。
    *   **去重与复用**：通过向量相似度，找出重复镜头或相似镜头。

### 1.4 Keyframe_maps (实体：视觉点) —— *被挖掘的宝藏 B*
*   **定位**：视觉风格与生成的种子。
*   **价值**：
    *   **卡点与定格**：音乐卡点剪辑需要精确到帧的视觉冲击力。只有帧级向量（CLIP Embedding）能捕捉瞬间。
    *   **AIGC 衍生**：作为 Image-to-Video 的 Prompt Image，配合向量库寻找“最适合转绘的帧”。

---

## 2. 改造规划 (Refactoring Plan)

### 阶段一：Schema 解耦与标准化 (Data Normalization)

**目标**：打破嵌套，建立引用。确保 Dialogues/Keyframes/Slices/Scenes 都有独立的 ID，互不包含实体副本，只存引用。

1.  **Dialogues (独立存储)**
    *   增加 `uuid` 字段。
    *   保持 `Material.dialogues` 为 **SSOT**。
    *   Workbench 的修改直接作用于此。

2.  **Keyframe_maps (独立存储)**
    *   增加 `uuid` 字段。
    *   将 `Material.keyframe_map` 视为独立的视觉资产表。
    *   **关键变更**：不再依附于 Slice ID 存储，而是扁平化存储，或者通过 TimeRange 索引。

3.  **Slices (引用重构)**
    *   **移除** `text_contents` (实体副本)，改为 `dialogue_ids` (引用)。
    *   **移除** `visual_contents` (实体副本)，改为 `keyframe_ids` (引用)。
    *   保留 `slice_analysis` (这是 Slice 独有的语义)。

4.  **Scenes (引用重构)**
    *   保持 `slice_ids` 引用。
    *   保留 `content` (叙事摘要)。

### 阶段二：向量化流水线 (Vectorization Pipeline)

**目标**：为四类数据建立独立的向量索引构建服务。引入 `IngestionService`。

| 数据类型 | 嵌入模型策略 (Embedding Strategy) | 触发时机 | 存储目标 |
| :--- | :--- | :--- | :--- |
| **Dialogues** | **Text Embedding** (e.g., BGE-M3, OpenAI). 侧重语义理解。 | Refinery 结束 / 人工修订后 | VectorDB Collection: `dialogues` |
| **Scenes** | **Text Embedding**. 输入为 `narrative_action` + `visual_mood`。 | Refinery 结束 / 人工修订后 | VectorDB Collection: `scenes` |
| **Slices** | **Multimodal Embedding**. 输入为 `visual_summary` + `tags` + `dialogue_text`。 | Refinery 结束 (无需人工) | VectorDB Collection: `slices` |
| **Keyframes** | **Image Embedding** (e.g., CLIP, SigLIP). 纯视觉特征。 | Refinery 结束 (无需人工) | VectorDB Collection: `keyframes` |

### 阶段三：数据流转与一致性设计 (Data Flow & Consistency)

1.  **Refinery 首次生成**：
    *   产生 V0 版数据 -> 触发 `BatchVectorizeTask` -> 写入向量库。

2.  **Workbench 人工修订 (Dialogues/Scenes)**：
    *   用户修改字幕/场景 -> 保存 -> 更新 PostgreSQL。
    *   **触发器**：后端检测到变更 -> 触发 `IncrementalUpdateTask` (增量更新)。
    *   **操作**：根据 ID 删除向量库旧数据 -> 生成新向量 -> 插入新数据。

3.  **Slices/Keyframes 的不可变性**：
    *   Slices (物理切片) 和 Keyframes (物理抽帧) 是客观存在的，人工极少修改。
    *   向量化通常是一次性的。

### 阶段四：应用层接口规划 (API Design)

封装查询服务以支持下游业务：

*   `search_assets(query, type=['slice', 'keyframe'], top_k=10)`: 用于素材挖掘。
*   `get_character_profile(character_name)`: 基于 Dialogue 向量聚合人物性格。
*   `match_beat_frames(music_rhythm, visual_tag)`: 结合音乐节奏和 Keyframe 向量寻找卡点素材。