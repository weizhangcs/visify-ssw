from pathlib import Path

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
from apps.atomflow.refinery.services.transcoder import TranscoderService
from apps.atomflow.refinery.services.uploader import TicketUploader
from apps.atomflow.refinery.services.vector_indexer import VectorIndexerService
from apps.atomflow.refinery.services.visual_analyzer import VisualAnalyzerService
from apps.common.cloud_client import CloudApiService

# ==============================================================================
# Service Adapters
# ==============================================================================


def _run_transcode(payload: dict, target_id: str):
    source_path = Path(payload["source_path"])
    abs_output_path = Path(payload["output_path"])
    abs_output_path.parent.mkdir(parents=True, exist_ok=True)
    TranscoderService.run(source_path, abs_output_path)
    return {"rel_path": payload["rel_path"]}


def _run_probe(payload: dict, target_id: str):
    abs_proxy_path = Path(payload["proxy_path"])
    temp_wav_path = Path(payload["temp_wav_path"])
    temp_wav_path.parent.mkdir(parents=True, exist_ok=True)
    tech_meta, duration, waveform = ProberService.run(abs_proxy_path, temp_wav_path)
    return {"duration": duration, "tech_meta": tech_meta, "waveform_data": waveform}


def _run_generate_hls(payload: dict, target_id: str):
    abs_proxy_path = Path(payload["proxy_path"])
    abs_output_dir = Path(payload["output_dir"])
    HLSGeneratorService.run(abs_proxy_path, abs_output_dir)
    return {"rel_path": payload["rel_path"]}


def _run_slice(payload: dict, target_id: str):
    slices = SlicerService.run(
        video_path=Path(payload["proxy_path"]),
        video_duration=payload["duration"],
        dialogues=payload["dialogues"],
        waveform_data=payload.get("waveform_data", []),
        scene_threshold=payload.get("scene_threshold", 0.3),
        dialogue_gap=payload.get("dialogue_gap", 1.0),
        max_pad=payload.get("max_pad", 0.5),
        silence_thresh=payload.get("silence_thresh", 0.02),
        lang=payload.get("lang", "zh"),
    )
    return {"slices": slices}


def _run_frame_extract(payload: dict, target_id: str):
    updated_slices = FrameExtractorService.run(
        video_path=Path(payload["proxy_path"]),
        slices=payload["slices"],
        abs_output_dir=Path(payload["output_dir"]),
        rel_output_dir=Path(payload["rel_dir"]),
    )
    return updated_slices


def _run_frame_probe(payload: dict, target_id: str):
    return FrameProberService.run(keyframe_map=payload["keyframe_map"], media_root=Path(payload["media_root"]))


def _run_text_analyze(payload: dict, target_id: str):
    client = CloudApiService()
    temp_file = Path(f"/tmp/subtitle_merge_input_{target_id}.json")
    try:
        dialogues = TextAnalyzerService.run(
            content=payload["content"],
            cloud_client=client,
            temp_file_path=temp_file,
            enable_semantic_merge=True,
            lang=payload.get("lang", "zh"),
        )
    finally:
        if temp_file.exists():
            temp_file.unlink()
    return {"dialogues": dialogues}


def _run_audio_analyze(payload: dict, target_id: str):
    updated_track = AudioAnalyzerService.run(
        video_path=Path(payload["video_path"]), dialogues=payload["dialogues"], lang=payload.get("lang", "zh")
    )
    return {"dialogues": updated_track}


def _run_character_refine(payload: dict, target_id: str):
    client = CloudApiService()
    asset_meta = {
        "video_title": payload["video_title"],
        "known_characters": payload["known_characters"],
        "lang": payload["lang"],
    }
    result_data = CharacterRefinerService.run(client, payload["dialogues"], asset_meta)
    updates = [item.model_dump() for item in result_data.identified_subtitles]
    return {"updates": updates}


def _run_synchronize(payload: dict, target_id: str):
    cloud_svc = CloudApiService()
    files_to_upload = [Path(p) for p in payload.get("files_to_upload", [])]
    uploader = TicketUploader(
        material_id=payload.get("material_id"), asset_id=payload.get("asset_id"), cloud_client=cloud_svc
    )
    mapping = uploader.upload_files(files_to_upload)
    return {"mapping": mapping}


def _run_analyze_visual(payload: dict, target_id: str):
    client = CloudApiService()
    result_data = VisualAnalyzerService.run(client, payload["frames"], payload["lang"])
    return result_data.model_dump()


def _run_analyze_slice(payload: dict, target_id: str):
    client = CloudApiService()
    return SliceAnalyzerService.run(
        client, payload["slices"], payload["keyframe_map"], payload["dialogues"], payload["lang"]
    )


def _run_regroup_slice(payload: dict, target_id: str):
    client = CloudApiService()
    result_data = SliceRegrouperService.run(client, payload["slices"], payload["dialogues"], payload["lang"])
    return result_data


def _run_verify_scene(payload: dict, target_id: str):
    return SceneVerifierService.run(
        video_path=Path(payload["video_path"]), scenes=payload["scenes"], output_dir=Path(payload["output_dir"])
    )


def _run_vector_index(payload: dict, target_id: str):
    VectorIndexerService.run(
        slices=payload["slices"], dialogues=payload["dialogues"], output_path=Path(payload["output_path"])
    )
    return {"rel_path": payload["rel_path"]}


# ==============================================================================
# Asset Service Adapters (聚合任务适配器)
# ==============================================================================


def _run_asset_global_character_refine(asset_id: str, pipeline_ids: list, config: dict):
    """
    [Asset Adapter] 全剧角色统筹
    """
    # 聚合任务通常直接操作数据库，不需要返回 Payload 给 Context 回填
    # 它的副作用体现在对多个 Pipeline/Material 的批量更新上
    GlobalCharacterRefinerService.run(asset_id, pipeline_ids)


# ==============================================================================
# Registry & Dispatcher
# ==============================================================================

SERVICE_REGISTRY = {
    "transcode": _run_transcode,
    "probe": _run_probe,
    "generate_hls": _run_generate_hls,
    "slice": _run_slice,
    "frame_extract": _run_frame_extract,
    "frame_probe": _run_frame_probe,
    "text_analyze": _run_text_analyze,
    "audio_analyze": _run_audio_analyze,
    "character_refine": _run_character_refine,
    "synchronize": _run_synchronize,
    "analyze_visual": _run_analyze_visual,
    "analyze_slice": _run_analyze_slice,
    "regroup_slice": _run_regroup_slice,
    "verify_scene": _run_verify_scene,
    "vector_index": _run_vector_index,
}

ASSET_SERVICE_REGISTRY = {
    "global_character_refine": _run_asset_global_character_refine,
    # 未来扩展: "global_scene_summary": _run_asset_global_scene_summary,
}


def dispatch_service_adapter(op_slug: str, payload: dict, target_id: str) -> dict:
    """
    [Registry Dispatcher] 查找并执行对应的 Service Adapter。
    """
    handler = SERVICE_REGISTRY.get(op_slug)
    if not handler:
        raise ValueError(f"Unknown operator slug: {op_slug}")

    return handler(payload, target_id)


def dispatch_asset_service_adapter(op_slug: str, asset_id: str, pipeline_ids: list, config: dict):
    """
    [Asset Registry Dispatcher] 查找并执行对应的 Asset Service Adapter。
    """
    handler = ASSET_SERVICE_REGISTRY.get(op_slug)
    if not handler:
        raise ValueError(f"Unknown asset operator slug: {op_slug}")

    handler(asset_id, pipeline_ids, config)
