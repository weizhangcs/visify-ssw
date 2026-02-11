# Atomflow 算子重组计划：面向能力的架构演进

## 1. 背景与目标

当前 Atomflow 的算子（Services）是按照业务场景（`Refinery` vs `Dubbing`）组织的。随着系统演进，我们发现大量算子具有通用性（如 OCR、ASR、VAD），目前的结构导致了：
1.  **职责边界模糊**：视频分析能力分散在两个业务目录下。
2.  **复用困难**：新业务场景难以直观地复用现有能力。

**目标**：从 **“面向业务流程 (Process-Oriented)”** 转型为 **“面向能力原子 (Capability-Oriented)”**。将算子按 **语义资产类型**（Audio/Video/Text/Multimodal）进行重组。

## 2. 核心架构变更

我们将 `apps/atomflow/` 下的目录结构调整为按模态分类。

### 2.1 新目录结构概览

```text
apps/atomflow/
├── audio/           # [听觉能力] 处理波形、频谱
│   └── services/
├── video/           # [视觉能力] 处理像素、帧、流
│   └── services/
├── text/            # [语义能力] 处理字符、实体、大语言模型
│   └── services/
├── multimodal/      # [融合能力] 处理跨模态对齐、高层理解
│   └── services/
└── common/          # [通用设施] 上传、工具类
    └── services/
```

## 3. 详细迁移映射表

### A. Audio (听觉能力)
*依赖: Torch, Torchaudio, Librosa, Whisper*

| 原路径 (Origin) | 新路径 (Target) | 说明 |
| :--- | :--- | :--- |
| `dubbing/services/separation.py` | `audio/services/separation.py` | 人声/伴奏分离 |
| `dubbing/services/gating.py` | `audio/services/gating.py` | VAD & 语义门控 |
| `dubbing/services/enhancement.py` | `audio/services/enhancement.py` | 语音降噪 |
| `dubbing/services/perception.py` | `audio/services/asr.py` | 语音转文字 (ASR) |
| `refinery/services/audio_analyzer.py` | `audio/services/analyzer.py` | 声学特征提取 (Pitch/Speed) |
| `dubbing/services/material.py` | `audio/services/mixing.py` | 音频混合/素材构建 |

### B. Video (视觉能力)
*依赖: OpenCV, FFmpeg, InsightFace, RapidOCR, LaMa*

| 原路径 (Origin) | 新路径 (Target) | 说明 |
| :--- | :--- | :--- |
| `refinery/services/transcoder.py` | `video/services/transcoder.py` | 视频转码 |
| `refinery/services/prober.py` | `video/services/prober.py` | 格式探测 |
| `refinery/services/hls_generator.py` | `video/services/hls.py` | HLS 切片 |
| `refinery/services/frame_extractor.py` | `video/services/frame_extractor.py` | 关键帧提取 |
| `refinery/services/frame_prober.py` | `video/services/frame_prober.py` | 帧质量检测 |
| `dubbing/services/ocr.py` | `video/services/ocr.py` | 画面文字提取 |
| `dubbing/services/visual.py` | `video/services/face.py` | 人脸检测与聚类 |
| `dubbing/services/inpainting.py` | `video/services/inpainting.py` | 画面擦除/去字幕 |
| `refinery/services/visual_analyzer.py` | `video/services/visual_llm.py` | VLM 画面理解 |
| `refinery/services/scene_verifier.py` | `video/services/scene_verifier.py` | 场景切分验证 |

### C. Text (文本/语义能力)
*依赖: LLM Client, Pandas, Regex*

| 原路径 (Origin) | 新路径 (Target) | 说明 |
| :--- | :--- | :--- |
| `refinery/services/text_analyzer.py` | `text/services/parser.py` | 字幕解析与清洗 |
| `dubbing/services/script_refinement.py` | `text/services/refinement.py` | 剧本精修 (ASR+OCR融合) |
| `dubbing/services/character.py` <br> `refinery/services/character_refiner.py` | `text/services/character.py` | 角色识别与归一化 (建议合并) |
| `refinery/services/global_character_refiner.py` | `text/services/global_character.py` | 全局角色一致性 |

### D. Multimodal (融合能力)
*依赖: 综合逻辑*

| 原路径 (Origin) | 新路径 (Target) | 说明 |
| :--- | :--- | :--- |
| `dubbing/services/fusion.py` | `multimodal/services/active_speaker.py` | 视听融合/活跃说话人检测 |
| `refinery/services/slicer.py` | `multimodal/services/slicer.py` | 智能切片 (视+听+文) |
| `refinery/services/slice_analyzer.py` | `multimodal/services/scene.py` | 场景分析 (Slice -> Scene) |
| `refinery/services/slice_regrouper.py` | `multimodal/services/regroup.py` | 场景聚类 |
| `refinery/services/vector_indexer.py` | `multimodal/services/vector_index.py` | 多模态向量索引 |

### E. Common (通用设施)

| 原路径 (Origin) | 新路径 (Target) | 说明 |
| :--- | :--- | :--- |
| `refinery/services/uploader.py` | `common/services/uploader.py` | 文件上传服务 |
| `dubbing/utils.py` | `common/utils/media_utils.py` | FFmpeg/Audio 工具类 |

## 4. 实施步骤

1.  **物理迁移**: 创建新目录，移动文件。
2.  **重构引用**:
    *   修改 `Service` 内部的 import (如 `apps.atomflow.dubbing.constants` -> `apps.atomflow.common.constants`)。
    *   修改 `Context` (编排层) 的 import，指向新的 Service 路径。
3.  **合并冗余**:
    *   合并 `dubbing/services/character.py` 和 `refinery/services/character_refiner.py` 为统一的 `CharacterService`。
    *   统一 `utils.py`。
4.  **测试验证**: 运行现有的 `tests/` 脚本，确保路径修正后功能正常。

## 5. 架构收益

*   **解耦**: 算子不再依赖于特定的业务上下文（Target/Material），回归纯粹的输入输出计算。
*   **复用**: 任何新的业务流程（如“视频搜索”、“切片二创”）都可以直接组装 `audio`、`video` 下的原子能力。
*   **清晰**: 目录结构即文档，开发者能快速定位到特定模态的处理逻辑。