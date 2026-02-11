# VSS Cloud 接口需求：Slice Regrouper (场景聚类与归纳)

## 1. 概述 (Overview)

`Slice Regrouper` 是 Refinery 流程的终点，也是一个高阶的**多模态融合**算子。它的职责是接收 Edge 端预处理完成的、富含文本和视觉语义的“富切片”列表，利用 LLM 的长上下文理解能力，完成两项核心任务：

1.  **场景聚类 (Clustering)**: 将叙事上连续的多个切片（Slices）聚类成一个场景（Scene）。
2.  **语义归纳 (Summarization)**: 为每个聚类出的场景生成结构化的语义描述。

## 2. 接口定义 (Interface)

*   **Endpoint**: `POST /api/v1/tasks/`
*   **Task Type**: `SLICE_REGROUPER`

### 2.1 请求参数 (Request Payload)

接口将采用**生产模式**，通过文件引用传递核心数据。

```json
{
    "task_type": "SLICE_REGROUPER",
    "payload": {
        "lang": "zh",
        "model": "models/gemini-1.5-pro-latest",
        "slices_file_path": "temp/rich_slices_for_regrouping.json"
    }
}
```

**文件内容格式 (`slices_file_path` 指向的文件):**

该文件是一个 `MultimodalSlice` 对象的列表。每个对象都包含了完整的文本和视觉分析结果。

```json
[
  {
    "slice_id": 1,
    "start_time": 0.0,
    "end_time": 5.2,
    "type": "dialogue",
    "text_contents": [
      {
        "index": 0,
        "content": "你好，世界。",
        "start_time": 1.0,
        "end_time": 2.5,
        "speaker": "角色A",
        "audio_analysis": { "gender": "Male", "..." }
      }
    ],
    "visual_contents": [
      {
        "frame_id": "uuid-...",
        "timestamp": 1.1,
        "path": "gs://...",
        "digest": "md5-...",
        "quality_score": 0.8,
        "visual_analysis": {
          "shot_type": "中景",
          "subject": "一个男人在说话",
          "..."
        }
      },
      "..."
    ]
  },
  "..."
]
```

#### 字段说明

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `lang` | string | 否 | 目标语言代码 (`zh`, `en`)。默认为 `zh`。 |
| `model` | string | 是 | 指定使用的 LLM 模型。**推荐使用具备长上下文处理能力的模型** (如 Gemini 1.5 Pro)。 |
| `slices_file_path` | string | 是 | 包含“富切片”列表的 JSON 文件路径。 |

### 2.2 响应结果 (Response Output)

任务完成后，输出结果将是一个 `Scene` 对象的列表。

```json
{
  "scenes": [
    {
      "scene_id": 1,
      "start_time": 0.0,
      "end_time": 15.8,
      "content": {
        "narrative_action": "角色A和角色B在咖啡馆初次相遇并进行了一段简短的对话。",
        "location": "室内-咖啡馆",
        "scene_type": "dialogue",
        "visual_mood_tags": ["温馨", "日常"],
        "camera_logic": "静态对话镜头",
        "character_dynamics": "初识，氛围平和",
        "reason": "Slices 1-3 在同一地点，且对话内容连续，构成一个完整的叙事单元。"
      },
      "slice_ids": [1, 2, 3]
    },
    "..."
  ],
  "stats": {
    "input_slice_count": 44,
    "output_scene_count": 8
  }
}
```

**字段说明 (对齐 `schema_models/scene.py`):**

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `scenes` | list | 聚类和归纳后的场景列表。 |
| `scene_id` | int | 场景的顺序 ID。 |
| `start_time` | float | 场景的起始时间（取最早 Slice 的 `start_time`）。 |
| `end_time` | float | 场景的结束时间（取最晚 Slice 的 `end_time`）。 |
| `content` | object | 场景的语义内容 (`SceneContent` 结构)。 |
| `slice_ids` | list[int] | 构成此场景的原始 `slice_id` 列表。 |

## 3. 核心逻辑要求

1.  **长上下文处理**: 服务必须能处理包含数千个切片（Slices）的完整输入，并进行全局分析。
2.  **场景边界识别**: LLM 的核心任务是判断相邻切片在**叙事、时间、空间、人物**上是否连续。
    *   **连续**: 属于同一场景。
    *   **不连续**: 场景发生切换，应切分。
3.  **结构化归纳**: 对每个识别出的场景，LLM 需要根据其包含的所有切片的文本和视觉信息，填写 `SceneContent` 中的所有字段。
4.  **时间轴合并**: 自动计算每个 `Scene` 的起止时间。

## 4. 提示词参考 (Prompt Reference)

> 你是一个顶级的电影剪辑师和剧本分析师。你的任务是将一系列按时间顺序排列的、富含多模态信息（文本、视觉）的“镜头切片” (Slices) 聚合成连贯的“场景” (Scenes)，并对每个场景进行深度分析。
>
> **输入**: 一个 JSON 列表，每个元素是一个 Slice，包含 `text_contents` (对白) 和 `visual_contents` (画面帧分析)。
>
> **你的任务**:
> 1.  **聚类 (Clustering)**: 仔细阅读所有 Slices，识别出场景的边界。当时间、地点、核心事件或人物发生显著变化时，通常意味着一个新场景的开始。
> 2.  **归纳 (Summarization)**: 对你划分出的每一个场景，生成一个结构化的 `SceneContent` 对象，填写以下字段：
>     *   `narrative_action`: 用一句话概括这个场景的核心事件或叙事动作。
>     *   `location`: 场景发生的主要地点。
>     *   `scene_type`: 场景的功能类型 (dialogue, action, montage, establishing, emotional, unknown)。
>     *   `visual_mood_tags`: 描述场景整体视觉氛围的标签。
>     *   `camera_logic`: 总结场景的运镜或剪辑风格。
>     *   `character_dynamics`: 描述场景中角色之间的关系或张力变化。
>     *   `reason`: 简要说明你为什么将这些 Slices 划分为一个场景。
>
> **输出**: 一个 JSON 对象，包含一个名为 `scenes` 的列表。