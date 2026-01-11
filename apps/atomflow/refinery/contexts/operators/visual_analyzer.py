import logging

from apps.atomflow.refinery.schemas import VisualAnalysisData

logger = logging.getLogger(__name__)


class VisualAnalyzerContextMixin:
    """
    Context Mixin for visual analysis via Cloud VLM.

    Provides methods to generate payloads for and handle results from the VisualAnalyzerService.
    """

    def _payload_visual_analyzer(self, target):
        """
        Generate payload for the VisualAnalyzerService.

        Strategy:
        - Filters for high-quality frames with cloud paths.
        - Deduplicates frames based on content digest to reduce redundant API calls.
        - Uses the digest as the unique 'frame_id' for mapping results.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing a list of unique frames to be analyzed,
            language, and the visual model name.
        """
        asset = getattr(target.media, "asset", None)
        lang = "en"  # Default to English
        if asset and asset.language:
            lang = asset.language.split("-")[0]

        # Collect unique frames based on digest
        unique_frames = {}

        if target.keyframe_map:
            for slice_id, frames in target.keyframe_map.items():
                for f in frames:
                    # 1. Quality Filter
                    if f.get("quality_score", 0) <= 0:
                        continue

                    # 2. Path Filter (must be a cloud path)
                    path = f.get("path")
                    if not path or not (path.startswith("http") or path.startswith("gs://")):
                        continue

                    # 3. Digest Filter (core deduplication logic)
                    digest = f.get("digest")
                    if not digest:
                        continue

                    if digest not in unique_frames:
                        unique_frames[digest] = {
                            "frame_id": digest,  # Use digest as the unique frame_id
                            "path": path,
                            "digest": digest,
                        }

        return {
            "frames": list(unique_frames.values()),
            "lang": lang,
        }

    def _handle_visual_analyzer(self, target, result):
        """
        Handle the result from the VisualAnalyzerService.

        Broadcasts the analysis results back to all frames in the keyframe_map
        that share the same content digest.

        Args:
            target: The Material instance.
            result: The full JSON response from the Cloud API.
        """
        annotated_frames = result.get("annotated_frames", [])
        if not annotated_frames:
            return

        # 1. Build a result map: digest (frame_id) -> visual_analysis
        analysis_map = {item["frame_id"]: item.get("visual_analysis", {}) for item in annotated_frames}

        # 2. Broadcast results back to the keyframe_map
        updated_map = {}
        if target.keyframe_map:
            for slice_id, frames in target.keyframe_map.items():
                updated_frames = []
                for frame_data in frames:
                    digest = frame_data.get("digest")

                    # If this frame's digest was analyzed, apply the result
                    if digest and digest in analysis_map:
                        try:
                            raw_data = analysis_map[digest].copy()

                            # Use Pydantic to validate and structure the data
                            va_data = VisualAnalysisData(**raw_data)
                            frame_data["visual_analysis"] = va_data.model_dump()
                        except Exception as e:
                            logger.warning(f"Failed to parse visual_analysis for digest {digest}: {e}")

                    updated_frames.append(frame_data)
                updated_map[slice_id] = updated_frames

        target.keyframe_map = updated_map

    def _check_visual_analyzer_ready(self, target):
        """
        Check if the Visual Analyzer task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if any frame in the keyframe_map has a cloud path.
        """
        # Depends on Sync being complete (i.e., keyframe_map has cloud paths)
        if not target.keyframe_map:
            return False
        return any(
            f.get("path", "").startswith(("http", "gs://")) for frames in target.keyframe_map.values() for f in frames
        )

    def _check_visual_analyzer_done(self, target):
        """
        Check if the Visual Analyzer task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if any frame in the keyframe_map has visual analysis data.
        """
        if not target.keyframe_map:
            return False
        return any(f.get("visual_analysis") is not None for frames in target.keyframe_map.values() for f in frames)
