import copy
from pathlib import Path
from typing import Dict

from apps.common.schemas.dataset.schemas import KeyframeItem


class SynchronizeContextMixin:
    """
    Context Mixin for synchronizing local files to cloud storage.

    Handles the preparation of file lists for upload and updates the
    Material's keyframe_map with cloud URLs after successful synchronization.
    """

    @property
    def media_root(self) -> Path:
        raise NotImplementedError

    def _payload_synchronize(self, target):
        """
        Generate payload for the SyncService (TicketUploader).

        Collects local file paths from the keyframe_map, filtering out
        low-quality frames and deduplicating based on file digests.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing a list of absolute file paths to upload,
            the asset ID, and the material ID.
        """
        asset_id = (
            str(target.media.asset.id) if hasattr(target.media, "asset") else "00000000-0000-0000-0000-000000000000"
        )

        files_to_upload = []
        seen_digests = set()

        # Collect frame paths from keyframe_map
        if target.keyframe_map:
            for slice_id, frames_list_dict in target.keyframe_map.items():
                for frame in frames_list_dict:
                    # 1. Quality Filter: Skip frames with low or zero quality score
                    q_score = frame.get("quality_score")
                    if q_score is not None and q_score <= 0.0:
                        continue

                    rel_path = frame.get("path")
                    # Only upload if it's a local path (not starting with http or gs://)
                    if rel_path and not rel_path.startswith(("http", "gs://")):
                        abs_path = self.media_root / rel_path
                        if abs_path.exists():
                            # 2. Digest Filter: Deduplicate based on content digest
                            digest = frame.get("digest")
                            if digest:
                                if digest in seen_digests:
                                    continue
                                seen_digests.add(digest)

                            files_to_upload.append(str(abs_path))

        files_to_upload = list(set(files_to_upload))

        return {"files_to_upload": files_to_upload, "asset_id": asset_id, "material_id": str(target.id)}

    def _handle_synchronize(self, target, result):
        """
        Handle the result from the SyncService.

        Updates the 'path' field in the keyframe_map with the cloud URL
        returned by the uploader. Uses digest-based broadcasting to update
        duplicate frames that were skipped during upload.

        Args:
            target: The Material instance.
            result: A dictionary containing a 'mapping' of local paths to cloud URLs.
        """
        mapping: Dict[str, str] = result.get("mapping", {})
        if not mapping or not target.keyframe_map:
            return

        # 1. Build Digest -> Cloud URL mapping (Broadcasting Source)
        # Since we deduplicated uploads, we need to map uploaded digests back to URLs
        digest_to_url = {}
        for slice_id, frames in target.keyframe_map.items():
            for frame in frames:
                path = frame.get("path")
                digest = frame.get("digest")
                if path and digest:
                    abs_path = str(self.media_root / path)
                    if abs_path in mapping:
                        digest_to_url[digest] = mapping[abs_path]

        updated_keyframe_map = copy.deepcopy(target.keyframe_map)
        for slice_id, frames_list_dict in updated_keyframe_map.items():
            for frame in frames_list_dict:
                digest = frame.get("digest")
                rel_path = frame.get("path")

                # Priority: Try to update via Digest broadcast (handles redundant frames)
                if digest and digest in digest_to_url:
                    frame["path"] = digest_to_url[digest]
                elif rel_path:
                    # Fallback: Try to update via Path mapping
                    abs_path = str(self.media_root / rel_path)
                    if abs_path in mapping:
                        frame["path"] = mapping[abs_path]

        # Ensure we write back valid FrameDataInput objects
        processed_map = {
            slice_id: [KeyframeItem(**frame_data).model_dump() for frame_data in frames]
            for slice_id, frames in updated_keyframe_map.items()
        }
        target.keyframe_map = processed_map

        # [Phase 1] 同步更新扁平化 frames
        all_frames = []
        for frames in processed_map.values():
            all_frames.extend(frames)
        target.frames = all_frames

    def _check_synchronize_ready(self, target):
        """
        Check if the Sync task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if keyframe_map is populated, False otherwise.
        """
        return bool(target.keyframe_map) and any(bool(v) for v in target.keyframe_map.values())

    def _check_synchronize_done(self, target):
        """
        Check if the Sync task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if any frame path in keyframe_map points to a cloud URL.
        """
        if not target.keyframe_map:
            return False
        # Check if any frame path has been updated to a cloud URL
        for slice_id, frames in target.keyframe_map.items():
            for frame in frames:
                if frame.get("path", "").startswith(("http", "gs://")):
                    return True
        return False
