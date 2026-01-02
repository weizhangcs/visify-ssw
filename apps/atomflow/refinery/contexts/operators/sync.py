import copy

from ...schemas import MultimodalSlice


class SyncContextMixin:
    def _payload_sync(self, target):
        asset_id = (
            str(target.media.asset.id) if hasattr(target.media, "asset") else "00000000-0000-0000-0000-000000000000"
        )

        files_to_upload = []
        for s in target.visual_slices:
            for frame in s.get("visual_contents", {}).get("frames", []):
                rel_path = frame.get("path")
                if rel_path and not rel_path.startswith("http"):
                    abs_path = self.media_root / rel_path
                    if abs_path.exists():
                        files_to_upload.append(str(abs_path))

        files_to_upload = list(set(files_to_upload))

        return {"files_to_upload": files_to_upload, "asset_id": asset_id, "material_id": str(target.id)}

    def _handle_sync(self, target, result):
        mapping = result.get("mapping", {})
        if not mapping:
            return

        updated_slices = copy.deepcopy(target.visual_slices)
        for s in updated_slices:
            for frame in s.get("visual_contents", {}).get("frames", []):
                rel_path = frame.get("path")
                if rel_path:
                    abs_path = self.media_root / rel_path
                    if str(abs_path) in mapping:
                        frame["path"] = mapping[str(abs_path)]

        target.visual_slices = [MultimodalSlice(**s).model_dump() for s in updated_slices]

    def _check_sync_ready(self, target):
        return bool(target.visual_slices)

    def _check_sync_done(self, target):
        if not target.visual_slices:
            return False
        first_slice = target.visual_slices[0]
        frames = first_slice.get("visual_contents", {}).get("frames", [])
        if not frames:
            return False
        return frames[0].get("path", "").startswith("http")
