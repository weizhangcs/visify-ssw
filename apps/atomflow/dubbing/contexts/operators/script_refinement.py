import logging

logger = logging.getLogger(__name__)


class ScriptRefinementContextMixin:
    """
    Context Mixin for Cloud Script Refinement.
    """

    def _payload_script_refinement(self, target):
        # 1. 获取 OCR LLM CSV 路径
        # DubbingSession.ocr_csv_path 存的是 'ocr_index.csv' (用于 Inpainting)
        # 我们需要同目录下的 'ocr_raw_for_llm.csv'
        ocr_llm_path = None
        if target.ocr_csv_path:
            # 假设 ocr_csv_path 是相对路径，结合 media_root 使用
            index_path = self.media_root / target.ocr_csv_path
            candidate = index_path.with_name("ocr_raw_for_llm.csv")

            if candidate.exists():
                ocr_llm_path = str(candidate)
            else:
                logger.warning(f"ScriptRefinement: OCR LLM file not found at {candidate}")

        # 2. 获取语言 (假设从 Material 关联的 Asset 获取，默认为中文)
        lang = "zh"
        if target.material and target.material.media and hasattr(target.material.media, "asset"):
            asset = target.material.media.asset
            if asset and asset.language:
                lang = asset.language.split("-")[0]

        return {"perception_data": target.perception_meta, "ocr_path": ocr_llm_path, "lang": lang}

    def _handle_script_refinement(self, target, result):
        # Result contains: refined_script (List), stats (Dict), usage_report (Dict)
        target.refined_script = result

    def _check_script_refinement_ready(self, target):
        # 依赖 ASR (perception_meta) 和 OCR (ocr_csv_path)
        return bool(target.perception_meta and target.ocr_csv_path)

    def _check_script_refinement_done(self, target):
        return bool(target.refined_script)
