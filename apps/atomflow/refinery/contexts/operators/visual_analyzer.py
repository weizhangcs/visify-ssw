import logging

from ...schemas import VisualAnalysisData

logger = logging.getLogger(__name__)


class VisualAnalyzerContextMixin:
    def _payload_visual_analyzer(self, target):
        """
        构造 Visual Analyzer 任务 Payload
        策略：基于 Digest 去重，仅发送唯一内容帧
        """
        asset = getattr(target.media, "asset", None)
        lang = "en"  # 默认英文
        if asset and asset.language:
            lang = asset.language.split("-")[0]

        # 收集唯一帧
        # digest -> frame_info
        unique_frames = {}

        if target.keyframe_map:
            for slice_id, frames in target.keyframe_map.items():
                for f in frames:
                    # 1. Quality Filter
                    if f.get("quality_score", 0) <= 0:
                        continue

                    # 2. Path Filter (必须是云端路径)
                    path = f.get("path")
                    if not path or not (path.startswith("http") or path.startswith("gs://")):
                        continue

                    # 3. Digest Filter (核心去重逻辑)
                    digest = f.get("digest")
                    if not digest:
                        continue

                    if digest not in unique_frames:
                        unique_frames[digest] = {
                            "frame_id": digest,  # [Key Point] 使用 Digest 作为 frame_id
                            "path": path,
                            "digest": digest,
                        }

        return {
            "frames": list(unique_frames.values()),
            "lang": lang,
            "visual_model": "models/gemini-2.5-flash",
        }

    def _handle_visual_analyzer(self, target, result):
        # result 应该是 Cloud API 返回的完整 JSON
        annotated_frames = result.get("annotated_frames", [])
        if not annotated_frames:
            return

        # 1. 建立结果映射: digest (frame_id) -> visual_analysis
        analysis_map = {item["frame_id"]: item.get("visual_analysis", {}) for item in annotated_frames}

        # 2. 广播回填到 keyframe_map
        updated_map = {}
        if target.keyframe_map:
            for slice_id, frames in target.keyframe_map.items():
                updated_frames = []
                for frame_data in frames:
                    digest = frame_data.get("digest")

                    # 如果该帧的 digest 在结果中，说明它（或它的孪生兄弟）被分析过了
                    if digest and digest in analysis_map:
                        try:
                            # 使用 Pydantic 校验并回填
                            va_data = VisualAnalysisData(**analysis_map[digest])
                            frame_data["visual_analysis"] = va_data.model_dump()
                        except Exception as e:
                            logger.warning(f"Failed to parse visual_analysis for digest {digest}: {e}")

                    updated_frames.append(frame_data)
                updated_map[slice_id] = updated_frames

        target.keyframe_map = updated_map

    def _check_visual_analyzer_ready(self, target):
        # 依赖 Sync 完成 (Keyframe Map 中有云端路径)
        if not target.keyframe_map:
            return False
        # 只要有任意一个 http/gs 路径，就认为 Ready
        return any(
            f.get("path", "").startswith(("http", "gs://")) for frames in target.keyframe_map.values() for f in frames
        )

    def _check_visual_analyzer_done(self, target):
        # 检查 keyframe_map 中是否有 visual_analysis 数据
        if not target.keyframe_map:
            return False
        return any(f.get("visual_analysis") is not None for frames in target.keyframe_map.values() for f in frames)
