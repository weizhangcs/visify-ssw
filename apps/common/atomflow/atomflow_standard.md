@shared_task(bind=True, retry_backoff=True)
def standard_pipeline_task(self, target_id, slug):
    """
    [Task 范式规范]
    1. 实例化上下文：隔离业务与工程。
    2. 执行算子：无状态调用。
    3. 结果回流：通过 Scheduler 驱动下一步。
    """
    # 获取特定业务的具体实现类
    # 例如：RefineryAtomicContext, RefineryService, RefineryScheduler
    atomic_ctx = ConcreteAtomicContext(target_id)
    pipeline_ctx = ConcretePipelineContext(target_id)

    try:
        # 点火：记录开始执行
        pipeline_ctx.mark_started(slug)
        
        # 转换：只处理业务
        success = ConcreteService.run(atomic_ctx)
        
        # 驱动：记录并寻找下一跳
        if success:
            ConcreteScheduler.record_and_dispatch(pipeline_ctx, slug)
        else:
            pipeline_ctx.mark_failed(slug, "Service logic returned False")
            
    except Exception as e:
        pipeline_ctx.mark_failed(slug, str(e))
        raise self.retry(exc=e) # 保持 Celery 的原生重试灵活性