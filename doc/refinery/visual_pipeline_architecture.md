# Visual Micro-LLM 数据流架构与去重策略

## 1. 核心概念与数据容器

在 Atomflow Refinery 的视觉处理链路中，存在两个核心数据容器，它们服务于不同的目的：

### 1.1 `visual_slices` (语义容器)
- **定位**: 业务结果的最终载体。
- **结构**: `List[MultimodalSlice]`。
- **特点**: **逻辑完整性优先**。
  - 为了保证后续的场景聚类、视频生成或平替剪辑，每个 Slice 必须包含完整的视觉信息（首帧、尾帧、中间帧）。
  - **允许冗余**: Slice A 的尾帧和 Slice B 的首帧如果是同一画面，在 `visual_slices` 中必须分别存在，以保证 A 和 B 作为独立单元的自洽性。

### 1.2 `keyframe_map` (生产索引)
- **定位**: 视觉处理过程中的中间态数据仓库。
- **结构**: `Dict[slice_id, List[FrameDataInput]]`。
- **特点**: **生产过程记录**。
  - 它是 `FrameExtractor` 的直接产出，记录了所有被提取出来的帧的物理信息、质量信息和分析结果。
  - 它是后续原子算子（Probe, Sync, Analyzer）的主要操作对象。

## 2. 标识符与映射关系

为了在“逻辑完整性”和“物理高效性”之间取得平衡，我们引入了三层映射机制：

1.  **Slice ID -> Frame ID (1:N)**
    -   **逻辑映射**。一个切片包含多个帧。
    -   每个 `FrameDataInput` 都有一个唯一的 UUID (`frame_id`)。即使两帧内容完全一样，它们的 `frame_id` 也是不同的。

2.  **Frame ID -> Digest (N:1)**
    -   **内容映射**。
    -   `digest` (MD5) 是帧内容的数字指纹。
    -   **关键点**: 这是去重的核心依据。如果 Slice A 的尾帧和 Slice B 的首帧指向同一个物理画面，它们的 `frame_id` 不同，但 `digest` 相同。

3.  **Digest -> Filepath (1:1)**
    -   **物理映射**。
    -   指向实际的磁盘文件或云端 URL。

## 3. 阶段性数据流转策略

整个 Visual Micro-LLM 流程在“全量处理”和“去重处理”之间交替进行，以最大化效率。

### 阶段 1: 生产 (FrameExtractor)
- **操作对象**: `visual_slices` -> `keyframe_map`
- **策略**: **全量逻辑生产，物理存储去重**。
  - 逻辑上：为每个 Slice 生成完整的 Start/Mid/End/Change 帧记录。
  - 物理上：使用基于时间戳的命名策略 (`frame_{timestamp}.jpg`)。如果两个 Slice 共享边界帧，它们会指向同一个物理文件，避免磁盘空间浪费。
  - **产出**: 填充 `keyframe_map`，计算并填充 `digest`。

### 阶段 2: 过滤 (FrameProbe)
- **操作对象**: `keyframe_map`
- **策略**: **全量遍历，计算缓存去重**。
  - 逻辑上：需要知道每一帧的质量（哪怕是重复帧），因为每个 Slice 都需要知道自己包含的帧是否可用。
  - 优化：利用 `processed_cache` (Key=Filepath)。如果遇到已处理过的文件路径，直接复用计算结果，避免重复的 OpenCV 开销。
- **产出**: 更新 `keyframe_map` 中的 `quality_score` 和 `filter_reason`。

### 阶段 3: 传输 (Sync)
- **操作对象**: `keyframe_map` -> Cloud Storage
- **策略**: **物理去重上传**。
  - 逻辑：
    1. **过滤**: 剔除 `quality_score <= 0` 的废片。
    2. **去重**: 收集所有合格帧的本地路径，使用 `Set` 去重。
  - **产出**: 将本地路径替换为云端 URL，回写至 `keyframe_map`。

### 阶段 4: 分析 (VisualAnalyzer)
- **操作对象**: `keyframe_map` -> Cloud VLM API
- **策略**: **运行时聚合发送，广播式回填**。
  - 这是成本最高的环节，必须严格去重。

  **A. 发送前 (聚合)**
  - 遍历 `keyframe_map`。
  - 建立一个临时映射 `unique_frames = Dict[digest, FrameData]`。
  - 仅将 `unique_frames.values()` (有效子集) 发送给 Cloud API。
  - *注：这里利用 Digest 隐式构建了“实际生产序列”。*

  **B. 接收后 (广播)**
  - Cloud API 返回结果 (Key=Frame ID of the unique frame)。
  - 建立结果映射 `result_map = Dict[digest, AnalysisResult]`。
  - **广播回填**: 再次遍历 `keyframe_map` 中的**所有帧**。
    - 计算当前帧的 `digest`。
    - 在 `result_map` 中查找对应的分析结果。
    - 如果命中，将结果写入当前帧的 `visual_analysis`。

  **效果**: Slice A 的尾帧和 Slice B 的首帧，虽然只发了一次请求，但都获得了相同的分析结果。

### 阶段 5: 业务聚合 (SliceRegrouper - Future)
- **操作对象**: `keyframe_map` + `dialogue_track` -> `visual_slices`
- **策略**: **逻辑回归**。
- 此时 `keyframe_map` 已经包含了完整的、经过清洗和分析的帧数据。
- Regrouper 根据业务逻辑，从 `keyframe_map` 中提取数据，组装成最终的业务结构，回填到 `visual_slices` 的 `visual_contents` 中，供前端展示或后续流程使用。

## 4. 总结

- **Visual Slices**: 只要逻辑完整，不惜物理冗余。
- **Keyframe Map**: 桥接逻辑与物理的数据库。
- **Digest**: 运行时去重与广播的唯一凭证。