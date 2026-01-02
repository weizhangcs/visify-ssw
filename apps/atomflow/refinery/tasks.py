import time
from pathlib import Path

from celery import shared_task

from apps.atomflow.refinery.services.character_refiner import CharacterRefinerService
from apps.atomflow.refinery.services.frame_extractor import FrameExtractorService
from apps.atomflow.refinery.services.hls_generator import HLSService
from apps.atomflow.refinery.services.probe import ProbeService
from apps.atomflow.refinery.services.slicer import SlicingService
from apps.atomflow.refinery.services.text_analyzer import TextAnalyzerService

# 引入具体的业务 Service
from apps.atomflow.refinery.services.transcoder import TranscodeService
from apps.atomflow.refinery.services.uploader import TicketUploader
from apps.workflow.common.cloud_client import CloudApiService

from .contexts import RefineryAtomicContext, RefineryPipelineContext
from .scheduler import RefineryAtomScheduler


@shared_task(bind=True, name="apps.atomflow.refinery.tasks.execute_step")
def refinery_atomic_task(self, pipeline_id, seq, op_slug):
    """
    [Task 范式实现]
    1. 隔离上下文
    2. 执行算子 (直接调用 apps.refinery.services)
    3. 结果回流
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


def _dispatch_service(op_slug: str, payload: dict, target_id: str) -> dict:
    """
    [内部适配器] 将 Context Payload 转换为 Service 参数，并规范化返回值
    """

    if op_slug == "transcode":
        source_path = Path(payload["source_path"])
        abs_output_path = Path(payload["output_path"])

        # 确保目录存在 (Task 层的副作用，允许)
        abs_output_path.parent.mkdir(parents=True, exist_ok=True)

        TranscodeService.run(source_path, abs_output_path)
        return {"rel_path": payload["rel_path"]}

    elif op_slug == "probe":
        abs_proxy_path = Path(payload["proxy_path"])
        temp_wav_path = Path(payload["temp_wav_path"])
        temp_wav_path.parent.mkdir(parents=True, exist_ok=True)

        tech_meta, duration, waveform = ProbeService.run(abs_proxy_path, temp_wav_path)
        return {"duration": duration, "tech_meta": tech_meta, "waveform_data": waveform}

    elif op_slug == "hls":
        abs_proxy_path = Path(payload["proxy_path"])
        abs_output_dir = Path(payload["output_dir"])

        HLSService.run(abs_proxy_path, abs_output_dir)
        return {"rel_path": payload["rel_path"]}

    elif op_slug == "slicing":
        abs_proxy_path = Path(payload["proxy_path"])
        duration = payload["duration"]
        dialogue_track = payload["dialogue_track"]
        waveform_data = payload.get("waveform_data", [])

        # Extract optional configs from payload if they exist
        scene_threshold = payload.get("scene_threshold", 0.3)
        dialogue_gap = payload.get("dialogue_gap", 1.0)
        max_pad = payload.get("max_pad", 0.5)
        silence_thresh = payload.get("silence_thresh", 0.02)

        slices = SlicingService.run(
            abs_proxy_path,
            duration,
            dialogue_track,
            waveform_data,
            scene_threshold=scene_threshold,
            dialogue_gap=dialogue_gap,
            max_pad=max_pad,
            silence_thresh=silence_thresh,
        )
        return {"slices": slices}

    elif op_slug == "frame_extract":
        abs_proxy_path = Path(payload["proxy_path"])
        slices = payload["slices"]
        abs_output_dir = Path(payload["output_dir"])
        rel_dir = Path(payload["rel_dir"])

        updated_slices = FrameExtractorService.run(abs_proxy_path, slices, abs_output_dir, rel_dir)
        return {"slices": updated_slices}

    elif op_slug == "text_analyze":
        # 数据读取已移至 Context
        dialogue = TextAnalyzerService.run(payload["content"])
        return {"dialogue_track": dialogue}

    elif op_slug == "character_refine":
        # 需要实例化 CloudClient
        client = CloudApiService()

        # 临时文件创建仍保留在 Task，因为这是 Service 接口要求的物理文件交互
        import json

        temp_json_path = Path(f"/tmp/dialogue_{target_id}.json")
        with open(temp_json_path, "w", encoding="utf-8") as f:
            json.dump(payload["dialogue_track"], f)

        asset_meta = {
            "video_title": payload["video_title"],
            "known_characters": payload["known_characters"],
            "lang": payload["lang"],
        }

        result_data = CharacterRefinerService.run(client, str(temp_json_path), asset_meta)

        # 获取增量更新数据 (通常只包含 index, speaker, reasoning)
        updates = result_data if isinstance(result_data, list) else result_data.get("dialogue_track", [])

        # 清理临时文件
        if temp_json_path.exists():
            temp_json_path.unlink()

        # 合并逻辑已移至 Context
        return {"updates": updates}

    elif op_slug == "sync":
        cloud_svc = CloudApiService()
        asset_id = payload.get("asset_id")
        material_id = payload.get("material_id")
        files_to_upload = [Path(p) for p in payload.get("files_to_upload", [])]

        uploader = TicketUploader(material_id=material_id, asset_id=asset_id, cloud_client=cloud_svc)

        # 执行批量上传 (返回 map: str(abs_path) -> cloud_url)
        mapping = uploader.upload_files(files_to_upload)

        # 回填逻辑已移至 Context
        return {"mapping": mapping}

    else:
        raise ValueError(f"Unknown operator slug: {op_slug}")
