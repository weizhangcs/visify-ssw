from pathlib import Path

from apps.atomflow.dubbing.services.enhancement import AudioEnhancementService
from apps.atomflow.dubbing.services.fusion import AudioVisualFusionService
from apps.atomflow.dubbing.services.gating import AudioGatingService
from apps.atomflow.dubbing.services.inpainting import InpaintingService
from apps.atomflow.dubbing.services.material import MaterialBuilderService
from apps.atomflow.dubbing.services.ocr import OCRService
from apps.atomflow.dubbing.services.perception import PerceptionAnalyzerService
from apps.atomflow.dubbing.services.script_refinement import ScriptRefinementService
from apps.atomflow.dubbing.services.separation import AudioSeparationService
from apps.atomflow.dubbing.services.visual import VisualAnalysisService


def _run_separation(payload, target_id):
    v, i = AudioSeparationService.run(Path(payload["input_path"]), Path(payload["output_dir"]))
    return (v, i)


def _run_gating(payload, target_id):
    return AudioGatingService.run(payload["vocals_path"], Path(payload["output_base"]))


def _run_enhancement(payload, target_id):
    return AudioEnhancementService.run(payload["vocals_path"], payload["mask_path"], payload["output_path"])


def _run_material(payload, target_id):
    return MaterialBuilderService.run(
        payload["inst_path"],
        payload["vocals_path"],
        payload["mask_path"],
        payload["enhanced_path"],
        payload["output_path"],
    )


def _run_analysis(payload, target_id):
    audio_path = Path(payload["audio_path"])
    # 优先使用 payload 指定的 output_path (通常是 perception.json)，否则回退到同名 json
    output_path = payload.get("output_path") or str(audio_path.with_suffix(".json"))
    return PerceptionAnalyzerService.run(str(audio_path), output_path=output_path)


def _run_ocr(payload, target_id):
    return OCRService.run(Path(payload["input_path"]), Path(payload["output_dir"]))


def _run_inpainting(payload, target_id):
    return InpaintingService.run(
        Path(payload["input_path"]), Path(payload["ocr_csv_path"]), Path(payload["output_path"])
    )


def _run_visual(payload, target_id):
    return VisualAnalysisService.run(
        Path(payload["video_path"]), Path(payload["output_dir"]), Path(payload["temp_dir"])
    )


def _run_fusion(payload, target_id):
    return AudioVisualFusionService.run(
        payload["metadata"], Path(payload["face_csv_path"]), Path(payload["audio_path"])
    )


def _run_script_refinement(payload, target_id):
    return ScriptRefinementService.run(
        payload["perception_data"], Path(payload["ocr_path"]) if payload["ocr_path"] else None, payload["lang"]
    )


SERVICE_REGISTRY = {
    "audio_separation": _run_separation,
    "audio_gating": _run_gating,
    "audio_enhancement": _run_enhancement,
    "audio_material_build": _run_material,
    "audio_perception_analyze": _run_analysis,
    "video_ocr": _run_ocr,
    "video_inpainting": _run_inpainting,
    "visual_analysis": _run_visual,
    "audio_visual_fusion": _run_fusion,
    "script_refinement": _run_script_refinement,
}


def dispatch_service_adapter(op_slug: str, payload: dict, target_id: str):
    handler = SERVICE_REGISTRY.get(op_slug)
    if not handler:
        raise ValueError(f"Unknown dubbing operator: {op_slug}")
    return handler(payload, target_id)
