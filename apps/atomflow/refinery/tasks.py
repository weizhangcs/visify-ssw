import copy
import time
from pathlib import Path

from celery import shared_task
from django.conf import settings

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

from .context import RefineryAtomicContext, RefineryPipelineContext
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
    media_root = Path(settings.MEDIA_ROOT)

    if op_slug == "transcode":
        source_path = Path(payload["source_video_path"])
        # 规划输出路径
        rel_path = f"refinery/{target_id}/proxy.mp4"
        abs_output_path = media_root / rel_path
        abs_output_path.parent.mkdir(parents=True, exist_ok=True)

        TranscodeService.run(source_path, abs_output_path)
        return {"rel_path": rel_path}

    elif op_slug == "probe":
        # 注意：payload 中的 proxy_path 可能是相对路径
        proxy_rel = payload["proxy_path"]
        abs_proxy_path = media_root / proxy_rel
        temp_wav_path = Path(payload["temp_wav_path"])
        temp_wav_path.parent.mkdir(parents=True, exist_ok=True)

        tech_meta, duration, waveform = ProbeService.run(abs_proxy_path, temp_wav_path)
        return {"duration": duration, "tech_meta": tech_meta, "waveform_data": waveform}

    elif op_slug == "hls":
        proxy_rel = payload["proxy_video_path"]
        abs_proxy_path = media_root / proxy_rel
        # 规划输出目录
        rel_dir = f"refinery/{target_id}/hls"
        abs_output_dir = media_root / rel_dir

        HLSService.run(abs_proxy_path, abs_output_dir)
        # HLS Service 返回的是 index.m3u8 的路径，或者我们约定返回目录
        # 这里假设我们需要存储 index.m3u8 的相对路径
        return {"rel_path": f"{rel_dir}/index.m3u8"}

    elif op_slug == "slicing":
        proxy_rel = payload["proxy_video_path"]
        abs_proxy_path = media_root / proxy_rel
        duration = payload["duration"]
        dialogue_track = payload["dialogue_track"]

        slices = SlicingService.run(abs_proxy_path, duration, dialogue_track)
        return {"slices": slices}

    elif op_slug == "frame_extract":
        proxy_rel = payload["proxy_video_path"]
        abs_proxy_path = media_root / proxy_rel
        slices = payload["slices"]

        # 规划输出目录
        rel_dir = Path(f"refinery/{target_id}/frames")
        abs_output_dir = media_root / rel_dir

        updated_slices = FrameExtractorService.run(abs_proxy_path, slices, abs_output_dir, rel_dir)
        return {"slices": updated_slices}

    elif op_slug == "text_analyze":
        # [修正] 从 SRT 文件读取内容
        subtitle_path = payload.get("subtitle_path")
        content = ""

        if subtitle_path:
            abs_path = media_root / subtitle_path
            if abs_path.exists():
                # 尝试读取，SRT 通常为 utf-8，但也可能是 utf-8-sig 或 gbk
                try:
                    content = abs_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    content = abs_path.read_text(encoding="gb18030", errors="ignore")

        dialogue = TextAnalyzerService.run(content)
        return {"dialogue_track": dialogue}

    elif op_slug == "character_refine":
        # 需要实例化 CloudClient
        client = CloudApiService()

        # 需要将 dialogue_track 转存为临时 JSON 文件供上传
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
        # 假设 result_data 直接就是更新后的 dialogue_track 列表，或者包含在某个字段中
        # 根据 CharacterRefinerService 代码，它返回 json.loads(content_bytes)
        # 假设返回格式为 {"dialogue_track": [...]} 或直接是 [...]
        # 这里做个防御性处理
        dialogue_track = result_data if isinstance(result_data, list) else result_data.get("dialogue_track", [])

        # 清理临时文件
        if temp_json_path.exists():
            temp_json_path.unlink()

        return {"dialogue_track": dialogue_track}

    elif op_slug == "sync":
        # [新增] 云端同步逻辑
        # 1. 初始化
        cloud_svc = CloudApiService()

        asset_id = payload.get("asset_id")
        if not asset_id:
            raise ValueError("Missing asset_id for sync operation")

        uploader = TicketUploader(material_id=target_id, asset_id=asset_id, cloud_client=cloud_svc)

        slices = payload.get("visual_slices", [])
        files_to_upload = []

        # 2. 收集所有帧文件
        for s in slices:
            for frame in s.get("frames", []):
                rel_path = frame.get("path")
                # 忽略已经是云端地址的 (http开头)
                if rel_path and not rel_path.startswith("http"):
                    abs_path = media_root / rel_path
                    if abs_path.exists():
                        files_to_upload.append(abs_path)

        # 去重
        files_to_upload = list(set(files_to_upload))

        # 3. 执行批量上传 (返回 map: str(abs_path) -> cloud_url)
        mapping = uploader.upload_files(files_to_upload)

        # 4. 更新 slices 中的路径为云端地址
        updated_slices = copy.deepcopy(slices)
        for s in updated_slices:
            for frame in s.get("frames", []):
                rel_path = frame.get("path")
                if rel_path:
                    abs_path = media_root / rel_path
                    # TicketUploader 返回的 key 是 str(abs_path)
                    if str(abs_path) in mapping:
                        frame["path"] = mapping[str(abs_path)]

        return {"slices": updated_slices}

    else:
        raise ValueError(f"Unknown operator slug: {op_slug}")
