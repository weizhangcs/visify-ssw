# Refinery Atomflow Architecture

本文档描述了 Refinery 子系统的核心工作流架构。采用 **自驱动 (Self-Driving / Choreography)** 模式：Scheduler 负责发令与决策，Task 负责执行并驱动下一跳。

## 核心工作流图

```mermaid
flowchart TD
    %% 定义角色和区域
    subgraph Control_Plane ["控制面 (Scheduler / Django)"]
        Start((开始))
        SCH_Start[Scheduler.start_pipeline]
        SCH_Dispatch[Scheduler.dispatch]
        SCH_Record[Scheduler.record_and_dispatch]
        DB[(PostgreSQL)]
        
        Decision_DAG{依赖检查<br/>DAG Logic}
        Decision_Finish{全流程结束?}
        Decision_Barrier{是 Asset<br/>聚合节点?}
    end

    subgraph Message_Queue ["中间件"]
        CeleryQ[[Celery Queue<br/>media_queue]]
    end

    subgraph Execution_Plane ["执行面 (Worker / Task)"]
        Task_Entry[Task.refinery_atomic_task]
        Ctx_Init[Context 初始化<br/>Pipeline/Atomic Ctx]
        Ctx_Payload[Context.get_payload]
        
        Registry[TaskRegistry<br/>dispatch_service_adapter]
        Service_Run["Service.run<br/>(FFmpeg/Cloud API)"]
        
        Ctx_Handle[Context.handle_result]
        Task_Err[异常处理 & Retry]
    end

    %% 流程连线
    Start --> SCH_Start
    SCH_Start -->|1. 状态置为 RUNNING| DB
    SCH_Start -->|2. 寻找无依赖的首个节点| SCH_Dispatch
    
    SCH_Dispatch -->|"3. 发送任务 (target_id, seq, slug)"| CeleryQ
    CeleryQ -->|4. 消费任务| Task_Entry
    
    Task_Entry --> Ctx_Init
    Ctx_Init -->|5. 状态置为 START| DB
    Ctx_Init --> Ctx_Payload
    Ctx_Payload -->|准备数据| Registry
    
    Registry -->|6. 查表分发| Service_Run
    Service_Run -->|执行业务逻辑| Service_Run
    
    Service_Run -- 成功 --> Ctx_Handle
    Service_Run -- 失败 --> Task_Err
    
    Ctx_Handle -->|7. 回填结果 & Metrics| DB
    Ctx_Handle -->|8. 唤醒调度器| SCH_Record
    
    SCH_Record -->|9. 状态置为 SUCCESS| DB
    SCH_Record --> Decision_DAG
    
    Decision_DAG -- 存在满足依赖的后续步骤 --> Decision_Barrier
    Decision_DAG -- 无后续步骤 --> Decision_Finish
    
    Decision_Barrier -- "No (原子任务)" --> SCH_Dispatch
    Decision_Barrier -- "Yes (聚合任务)" --> Barrier_Logic[Handle Asset Barrier]
    
    Decision_Finish -- Yes --> End((流程完成))
    
    %% 样式
    style SCH_Dispatch fill:#e1f5fe,stroke:#01579b
    style SCH_Record fill:#e1f5fe,stroke:#01579b
    style Task_Entry fill:#fff3e0,stroke:#e65100
    style Service_Run fill:#f3e5f5,stroke:#4a148c
```

## 关键组件职责

1.  **Scheduler (`scheduler.py`)**: 无状态的决策大脑。
    *   负责计算 DAG 依赖。
    *   负责处理 Barrier 同步。
    *   不直接依赖具体的 Service 实现。

2.  **Task (`tasks.py`)**: 通用的执行容器。
    *   负责 Context 的生命周期管理。
    *   通过 `task_registry` 将抽象的 `slug` 映射为具体的代码执行。
    *   执行完成后，主动调用 Scheduler 进行状态流转。