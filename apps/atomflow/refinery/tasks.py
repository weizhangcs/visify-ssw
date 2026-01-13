import time
from pathlib import Path

from celery import shared_task

from apps.atomflow.refinery.contexts.atomic import RefineryAtomicContext
from apps.atomflow.refinery.contexts.pipeline import RefineryPipelineContext
from apps.atomflow.refinery.scheduler import RefineryAtomScheduler
from apps.atomflow.refinery.services.audio_analyzer import AudioAnalyzerService
from apps.atomflow.refinery.services.character_refiner import CharacterRefinerService
from apps.atomflow.refinery.services.frame_extractor import FrameExtractorService
from apps.atomflow.refinery.services.frame_prober import FrameProberService
from apps.atomflow.refinery.services.global_character_refiner import GlobalCharacterRefinerService
from apps.atomflow.refinery.services.hls_generator import HLSGeneratorService
from apps.atomflow.refinery.services.prober import ProberService
from apps.atomflow.refinery.services.scene_verifier import SceneVerifierService
from apps.atomflow.refinery.services.slice_analyzer import SliceAnalyzerService
from apps.atomflow.refinery.services.slice_regrouper import SliceRegrouperService
from apps.atomflow.refinery.services.slicer import SlicerService
from apps.atomflow.refinery.services.text_analyzer import TextAnalyzerService

# 引入具体的业务 Service
from apps.atomflow.refinery.services.transcoder import TranscoderService
from apps.atomflow.refinery.services.uploader import TicketUploader
from apps.atomflow.refinery.services.vector_indexer import VectorIndexerService
from apps.atomflow.refinery.services.visual_analyzer import VisualAnalyzerService
from apps.common.cloud_client import CloudApiService


@shared_task(bind=True, name="apps.atomflow.refinery.tasks.execute_step")
def refinery_atomic_task(self, pipeline_id, seq, op_slug):
    """
    [Task] Refinery 原子任务执行入口。

    遵循 Atomflow 标准范式：
    1. Context Isolation: 初始化 Pipeline 和 Atomic 上下文。
    2. Payload Extraction: 从 Atomic Context 获取纯净输入数据。
    3. Execution: 调用 _dispatch_service 分发到具体的 Service 执行。
    4. Result Handling: 将结果回填至 Atomic Context。
    5. Scheduling: 记录 Metrics 并驱动 Scheduler 进行下一跳。

    Args:
        pipeline_id: 当前执行的 Pipeline ID。
        seq: 当前步骤在规则中的序号。
        op_slug: 算子标识符 (如 transcode, probe)。
    """
    pipe_ctx = RefineryPipelineContext(pipeline_id)
    # 修正：RefineryPipelineContext.pipeline.target_id 是 CharField，但我们需要传递给 AtomicContext
    # AtomicContext 内部会处理 target_id
    target_id = pipe_ctx.pipeline.target_id
    atomic_ctx = RefineryAtomicContext(target_id)

    # 记录开始状态，传入 slug
    start_time = time.time()
    pipe_ctx.transit_state(seq, op_slug, "START")

    try:
        # A. 转换：获取 Payloads
        payload = atomic_ctx.get_payload(op_slug)

        # B. 执行：分发到具体的 Service 并适配参数
        result = _dispatch_service(op_slug, payload, target_id)

        # C. 驱动：回填业务数据
        atomic_ctx.handle_result(op_slug, result)

        # [Fix] 强制刷新 Pipeline 状态
        # atomic_ctx.handle_result 更新了数据库中的 metrics (SUCCESS)
        # 但 pipe_ctx.pipeline 实例中的 metrics 仍然是旧的 (START)
        # Scheduler 依赖最新的 metrics 来判断依赖关系，否则无法触发下一步
        pipe_ctx.pipeline.refresh_from_db()

        # D. 结果回流至 Scheduler
        duration = time.time() - start_time
        # record_and_dispatch 内部会自动 transit_state(seq, "SUCCESS")
        # [Fix] mode 属性在 rule 上，不在 pipeline 上
        RefineryAtomScheduler.record_and_dispatch(
            pipe_ctx=pipe_ctx, current_seq=seq, mode=pipe_ctx.pipeline.rule.mode, duration=duration
        )

    except Exception as e:
        # 记录失败状态，传入 slug
        pipe_ctx.transit_state(seq, op_slug, "FAIL", error_msg=str(e))
        raise self.retry(exc=e)


@shared_task(bind=True, name="apps.atomflow.refinery.tasks.execute_asset_step")
def execute_asset_step(self, asset_id, pipeline_ids, step_config):
    """
    [Task] Asset 级别聚合任务执行入口 (Barrier/Reduce)。

    职责：
    1. 执行聚合逻辑 (如 Global Character Refine)。
    2. 更新所有涉及 Pipeline 的状态为 SUCCESS。
    3. 唤醒所有 Pipeline 继续执行 (Resume)。
    """
    from apps.atomflow.refinery.models import RefineryAtomPipeline

    op_slug = step_config["unit_slug"]
    seq = step_config["seq"]

    # 1. 执行聚合业务逻辑
    try:
        if op_slug == "global_character_refine":
            GlobalCharacterRefinerService.run(asset_id, pipeline_ids)
        else:
            # 扩展点：未来可能有 global_scene_summary 等
            pass
    except Exception as e:
        # 如果聚合失败，所有 Pipeline 标记为 FAIL
        # 或者只标记当前 Task 失败，等待重试
        raise self.retry(exc=e)

    # 2. 唤醒所有 Pipeline (Resume)
    pipelines = RefineryAtomPipeline.objects.filter(id__in=pipeline_ids)

    for pipeline in pipelines:
        # 更新 Metrics 为 SUCCESS
        metrics = pipeline.metrics or {}
        metrics[str(seq)] = {"slug": op_slug, "status": "SUCCESS", "finished_at": time.time()}
        pipeline.metrics = metrics
        pipeline.save(update_fields=["metrics"])

        # 驱动下一跳
        pipe_ctx = RefineryPipelineContext(str(pipeline.id))
        RefineryAtomScheduler.record_and_dispatch(
            pipe_ctx=pipe_ctx, current_seq=seq, mode=pipeline.rule.mode, duration=0  # 聚合任务耗时难以分摊，暂记0
        )


def _dispatch_service(op_slug: str, payload: dict, target_id: str) -> dict:
    """
    [内部适配器] Service 分发与参数适配。

    职责：
    1. 将 Context 提供的字典 Payload 转换为 Service 所需的强类型参数 (如 Path 对象)。
    2. 处理部分临时文件路径的规划 (如 output_path)。
    3. 调用具体的 Service.run 方法。
    4. 将 Service 返回值规范化为字典，供 Context 回填。

    Args:
        op_slug: 算子标识符。
        payload: 输入数据字典。
        target_id: 目标对象 ID (用于路径规划)。

    Returns:
        执行结果字典。
    """
    if op_slug == "transcode":
        source_path = Path(payload["source_path"])
        abs_output_path = Path(payload["output_path"])

        # 确保目录存在 (Task 层的副作用，允许)
        abs_output_path.parent.mkdir(parents=True, exist_ok=True)

        TranscoderService.run(source_path, abs_output_path)
        return {"rel_path": payload["rel_path"]}

    elif op_slug == "probe":
        abs_proxy_path = Path(payload["proxy_path"])
        temp_wav_path = Path(payload["temp_wav_path"])
        temp_wav_path.parent.mkdir(parents=True, exist_ok=True)

        tech_meta, duration, waveform = ProberService.run(abs_proxy_path, temp_wav_path)
        return {"duration": duration, "tech_meta": tech_meta, "waveform_data": waveform}

    elif op_slug == "generate_hls":
        abs_proxy_path = Path(payload["proxy_path"])
        abs_output_dir = Path(payload["output_dir"])

        HLSGeneratorService.run(abs_proxy_path, abs_output_dir)
        return {"rel_path": payload["rel_path"]}

    elif op_slug == "slice":
        abs_proxy_path = Path(payload["proxy_path"])
        duration = payload["duration"]
        dialogues = payload["dialogues"]
        waveform_data = payload.get("waveform_data", [])
        lang = payload.get("lang", "zh")

        # Extract optional configs from payload if they exist
        scene_threshold = payload.get("scene_threshold", 0.3)
        dialogue_gap = payload.get("dialogue_gap", 1.0)
        max_pad = payload.get("max_pad", 0.5)
        silence_thresh = payload.get("silence_thresh", 0.02)

        slices = SlicerService.run(
            abs_proxy_path,
            duration,
            dialogues,
            waveform_data,
            scene_threshold=scene_threshold,
            dialogue_gap=dialogue_gap,
            max_pad=max_pad,
            silence_thresh=silence_thresh,
            lang=lang,
        )
        return {"slices": slices}

    elif op_slug == "frame_extract":
        abs_proxy_path = Path(payload["proxy_path"])
        slices = payload["slices"]
        abs_output_dir = Path(payload["output_dir"])
        rel_dir = Path(payload["rel_dir"])

        updated_slices = FrameExtractorService.run(abs_proxy_path, slices, abs_output_dir, rel_dir)
        return updated_slices  # FrameExtractorService 现在直接返回 keyframe_map

    elif op_slug == "frame_probe":
        keyframe_map = payload["keyframe_map"]  # 接收的是 Dict[str, List[Dict]]
        media_root_path = Path(payload["media_root"])
        updated_keyframe_map = FrameProberService.run(keyframe_map, media_root_path)
        return updated_keyframe_map  # FrameProbeService 现在直接返回更新后的 keyframe_map

    elif op_slug == "text_analyze":
        # [Update] 注入 Cloud Client 支持语义合并
        client = CloudApiService()
        content = payload["content"]
        # 假设 payload 中可能包含 lang，如果没有则默认为 zh
        lang = payload.get("lang", "zh")

        temp_file = Path(f"/tmp/subtitle_merge_input_{target_id}.json")
        try:
            dialogues = TextAnalyzerService.run(
                content,
                cloud_client=client,
                temp_file_path=temp_file,
                enable_semantic_merge=True,
                lang=lang,
            )
        finally:
            if temp_file.exists():
                temp_file.unlink()
        return {"dialogues": dialogues}

    elif op_slug == "audio_analyze":
        video_path = Path(payload["video_path"])
        dialogues = payload["dialogues"]
        lang = payload.get("lang", "zh")
        updated_track = AudioAnalyzerService.run(video_path, dialogues, lang=lang)
        return {"dialogues": updated_track}

    elif op_slug == "character_refine":
        # 需要实例化 CloudClient
        client = CloudApiService()

        asset_meta = {
            "video_title": payload["video_title"],
            "known_characters": payload["known_characters"],
            "lang": payload["lang"],
        }

        # [Update] 直接传递数据，Service 负责 Schema 转换和上传
        result_data = CharacterRefinerService.run(client, payload["dialogues"], asset_meta)

        # [Schema Update] result_data 是 CharacterIdentifierResponse 对象
        updates = [item.model_dump() for item in result_data.identified_subtitles]

        # 合并逻辑已移至 Context
        return {"updates": updates}

    elif op_slug == "synchronize":
        cloud_svc = CloudApiService()
        asset_id = payload.get("asset_id")
        material_id = payload.get("material_id")
        files_to_upload = [Path(p) for p in payload.get("files_to_upload", [])]

        uploader = TicketUploader(material_id=material_id, asset_id=asset_id, cloud_client=cloud_svc)

        # 执行批量上传 (返回 map: str(abs_path) -> cloud_url)
        mapping = uploader.upload_files(files_to_upload)

        # 回填逻辑已移至 Context
        return {"mapping": mapping}

    elif op_slug == "analyze_visual":
        client = CloudApiService()
        frames = payload["frames"]
        lang = payload["lang"]
        result_data = VisualAnalyzerService.run(client, frames, lang)
        return result_data.model_dump()

    elif op_slug == "analyze_slice":
        client = CloudApiService()
        # SliceAnalyzer 负责 Hydration，所以需要 keyframe_map
        # [Phase 1] 传递 dialogues 用于文本回填
        return SliceAnalyzerService.run(
            client, payload["slices"], payload["keyframe_map"], payload["dialogues"], payload["lang"]
        )

    elif op_slug == "regroup_slice":
        client = CloudApiService()
        slices = payload["slices"]
        lang = payload["lang"]
        result_data = SliceRegrouperService.run(client, slices, payload["dialogues"], lang)
        return result_data.model_dump()

    elif op_slug == "verify_scene":
        video_path = Path(payload["video_path"])
        scenes = payload["scenes"]
        output_dir = Path(payload["output_dir"])
        return SceneVerifierService.run(video_path, scenes, output_dir)

    elif op_slug == "vector_index":
        slices = payload["slices"]
        dialogues = payload["dialogues"]
        abs_output_path = Path(payload["output_path"])
        VectorIndexerService.run(slices, dialogues, abs_output_path)
        return {"rel_path": payload["rel_path"]}

    else:
        raise ValueError(f"Unknown operator slug: {op_slug}")
