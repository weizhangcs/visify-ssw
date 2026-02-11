# FrameProbeService 设计文档

## 1. 概述 (Overview)

`FrameProbeService` 是 Atomflow Refinery 中 **Visual Micro-LLM** 流程的关键一环。它的核心职责是作为一个高效的 **“质量守门员” (Quality Gate)**，在帧数据被同步到云端并提交给昂贵的 VLM (视觉大模型) 进行分析之前，对每一帧进行低成本的本地质量预检。

此算子的设计严格遵循 **降维** 和 **聚焦** 的原则：

- **降维**：它不负责描述画面内容（如亮度、色彩），因为这是 VLM 的核心能力。在 Edge 端进行此类分析是冗余的，并可能引入噪音。
- **聚焦**：它只专注于两件事：**质量过滤** 和 **性能优化**。

## 2. 在流程中的位置 (Position in Pipeline)

`FrameProbeService` 紧跟在 `FrameExtractorService` 之后，并位于 `SyncService` 之前。

```
... -> Slicer -> FrameExtractor -> [FrameProbe] -> Sync -> VisualAnalyzer -> ...
```

1.  **输入**: `FrameExtractor` 生成的 `keyframe_map`。这是一个以 `slice_id` 为键，值为 `List[FrameDataInput]` 的字典。
2.  **输出**: 一个更新后的 `keyframe_map`。其中，每个 `FrameDataInput` 对象的 `quality_score` 和 `filter_reason` 字段被填充。

## 3. 核心逻辑 (Core Logic)

### 3.1 质量过滤 (Quality Filtering)

这是 `FrameProbe` 的首要职责。它通过一系列低成本的 OpenCV 计算，为每一帧打上“可用”或“不可用”的标签。

#### 3.1.1 黑/白帧检测

- **方法**: `_is_black_or_white_frame()`
- **原理**: 计算图像灰度图的**平均像素值 (mean)** 和**标准差 (std)**。
  - 如果 `mean` 和 `std` 都极低 (e.g., `mean < 10`, `std < 5`)，则判定为 **黑帧**。
  - 如果 `mean` 极高而 `std` 极低 (e.g., `mean > 245`, `std < 5`)，则判定为 **白帧**。
- **结果**: 如果检测为黑/白帧，`filter_reason` 字段将被标记为 `"black_frame"` 或 `"white_frame"`。

#### 3.1.2 极度模糊检测

- **方法**: 计算拉普拉斯方差 (Laplacian Variance)。
- **原理**: 拉普拉斯算子用于检测图像的边缘。对于清晰的图像，边缘丰富，方差值较高；对于模糊的图像，边缘稀疏，方差值较低。
- **结果**: 如果方差值低于一个预设阈值 (e.g., `fm < 100.0`)，则认为该帧过于模糊，`filter_reason` 字段将被标记为 `"blurry_frame"`。

#### 3.1.3 综合质量分 (`quality_score`)

- **定位**: 这是一个纯粹的 **“可用性”** 分数，而非“描述性”分数。
- **计算**:
  - 如果 `filter_reason` 存在（即被判定为黑/白/模糊帧），`quality_score` 直接置为 **`0.0`**。
  - 否则，`quality_score` 由一个简化的公式计算得出 (e.g., `fm / 1000.0`)，仅用于在“可用”的帧中进行相对排序。
- **作用**: 下游算子（如 `Sync`）可以简单地通过 `quality_score > 0.0` 来过滤掉所有不可用的帧。

### 3.2 性能优化：基于路径的计算缓存 (Path Caching)

#### 3.2.1 问题背景

`FrameExtractor` 的抽帧策略（首/中/尾/变化）可能会导致多个 `FrameDataInput` 对象指向同一个物理文件。最典型的例子是：

> Slice A 的**尾帧**和 Slice B 的**首帧**，如果时间戳相同，它们会指向同一个 `frame_{timestamp}.jpg` 文件。

如果不做处理，`FrameProbe` 会对这个文件进行两次重复的 OpenCV 计算。

#### 3.2.2 解决方案

- **机制**: 在 `run` 方法内部，维护一个 `processed_cache` 字典。
- **键 (Key)**: 帧的物理绝对路径字符串 (`str(abs_path)`)。
- **值 (Value)**: 一个元组，包含计算出的 `(quality_score, filter_reason)`。
- **流程**:
  1. 在处理每一帧前，先检查其路径是否在 `processed_cache` 中。
  2. **命中 (Hit)**: 如果存在，直接从缓存中读取结果并填充到 `FrameDataInput` 对象中，然后跳过所有计算，进入下一帧的处理。
  3. **未命中 (Miss)**: 如果不存在，则正常执行 OpenCV 计算，并将计算结果存入缓存，以备后续使用。

#### 3.2.3 效果

通过路径缓存，我们确保了**每个物理文件只被分析一次**，极大地提升了 `FrameProbe` 的整体执行效率，尤其是在切片数量庞大的情况下。

## 4. Schema 依赖

`FrameProbeService` 的输入和输出都强依赖于 `FrameDataInput` 的结构。

```python
class FrameDataInput(BaseModel):
    # ... (其他字段)
    quality_score: Optional[float]
    filter_reason: Optional[str]
```

任何对 `quality_score` 或 `filter_reason` 字段的修改，都需要同步更新此文档和相关代码。