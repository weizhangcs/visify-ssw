# VSS Edge 数据契约重构方案 (Schema Refactoring)

## 1. 背景与问题 (Context & Problem)

在构建 `RetrievalHub` (RAG) 过程中，我们发现系统存在 **“数据契约漂移” (Schema Drift)** 问题，导致下游无法正确消费上游产生的数据。

### 1.1 现状 (Current State)
目前系统中存在两套相似但隔离的数据定义：
1.  **Refinery Schemas (Domain Model)**:
    *   位置: `apps.atomflow.refinery.schemas`
    *   特点: 结构严谨，使用 `LabelValue` (Value + Label) 对象存储枚举，服务于核心算法和后端逻辑。
    *   地位: 应作为系统的 **单一事实来源 (SSOT)**。
2.  **Workbench Schemas (View Model)**:
    *   位置: `apps.common.schemas.annotation.workbench`
    *   特点: 结构扁平，使用 `str` 存储枚举 (如 `"action"`)，包含大量 UI 状态字段 (`is_verified`)。
    *   地位: 服务于前端 React 组件交互。

### 1.2 冲突点 (The Conflict)
*   **数据生产**: `AnnotationService` 目前直接将 **Workbench Schema** (扁平结构) 存入数据库的 `AnnotationJob.scenes` 等字段。
*   **数据消费**: `RetrievalHub` 期望读取 **Refinery Schema** (严谨结构) 以进行高质量的语义检索和上下文构建。
*   **结果**: 下游在反序列化时报错 (e.g., `Input should be a valid dictionary`)，且丢失了 Label 等元信息。

## 2. 重构目标 (Objectives)

建立清晰的 **CQRS (命令查询职责分离)** 边界，确保持久化的业务数据严格符合核心领域模型。

*   **AnnotationJob.data (保留现状)**: 继续存储 **Workbench Schema**，作为“草稿/工作区状态”，服务于前端编辑器，保持交互灵活性。
*   **AnnotationJob.scenes/dialogues (重构目标)**: 必须存储 **Refinery Schema**，作为“已发布产出物 (Published Artifacts)”，服务于 RAG、渲染引擎和导出模块。

## 3. 详细设计 (Detailed Design)

### 3.1 共享内核 (Shared Kernel)
建立枚举值的统一引用，防止定义分叉。

*   **Action**: 修改 `apps.common.schemas.annotation.workbench`。
*   **Change**: 不再重新定义 `SceneType` 等枚举，改为引用 `apps.atomflow.refinery.schemas` 中的定义，或确保其 Value 值域严格一致。

### 3.2 防腐层实现 (Anti-Corruption Layer)
在数据持久化阶段引入 **转换 (Translation)** 和 **校验 (Validation)** 逻辑。

*   **Location**: `apps/workflow/annotation/services/annotation_service.py`
*   **Method**: `publish_job_artifacts(job)`
*   **Logic**:
    1.  **Input**: 读取 `job.data` (Workbench Schema)。
    2.  **Transform**: 编写转换器，将扁平数据“升维”为领域对象。
        *   Example: `scene_type="action"` -> `scene_type={"value": "action", "label": "动作场"}`
    3.  **Validate**: 使用 `Refinery.Scene(**data)` 进行严格校验。
    4.  **Output**: 将校验后的数据写入 `job.scenes`。

### 3.3 数据流向图 (Data Flow)

```mermaid
graph TD
    Frontend[React Workbench]
    
    subgraph "Database (AnnotationJob)"
        JobData[Field: data<br/>(Stores Workbench Schema)]
        JobArtifacts[Field: scenes/dialogues<br/>(Stores Refinery Schema)]
    end

    subgraph "Service Layer"
        Service[AnnotationService]
        ACL[Anti-Corruption Layer<br/>(Transformer & Validator)]
    end

    Frontend <-->|JSON (Flat)| JobData
    
    JobData -->|Publish Trigger| Service
    Service -->|Raw Data| ACL
    ACL -->|Hydrated Domain Objects| JobArtifacts
    
    JobArtifacts -->|Read| RAG[Retrieval Hub]
    JobArtifacts -->|Read| Export[Export Service]
```

## 4. 迁移计划 (Migration Plan)

由于业务尚未发布，无需考虑存量数据清洗 (Data Migration)。

1.  **Step 1**: 修改 Workbench Schema 定义，使其枚举值与 Refinery 对齐。
2.  **Step 2**: 重写 `AnnotationService.publish_job_artifacts`，实现转换逻辑。
3.  **Step 3**: 运行 `tests/retrieval` 测试，验证 RAG 能否正确读取新生成的数据。

## 5. 收益 (Benefits)

1.  **全链路一致性**: 从生产到消费，数据结构保持一致，消除隐式依赖。
2.  **代码简化**: 下游应用 (RAG) 无需编写复杂的兼容代码 (`if isinstance(x, str)...`)。
3.  **类型安全**: 数据库中的产出物字段由 Pydantic 严格守护，杜绝脏数据。