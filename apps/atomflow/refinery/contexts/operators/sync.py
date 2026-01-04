import copy
from typing import Dict

from ...schemas import FrameDataInput


class SyncContextMixin:
    def _payload_sync(self, target):
        asset_id = (
            str(target.media.asset.id) if hasattr(target.media, "asset") else "00000000-0000-0000-0000-000000000000"
        )

        files_to_upload = []
        seen_digests = set()

        # [Fix] 从 keyframe_map 中获取要上传的帧路径
        if target.keyframe_map:
            for slice_id, frames_list_dict in target.keyframe_map.items():
                for frame in frames_list_dict:
                    # 1. Quality Filter: 过滤掉质量分低或为0的帧
                    q_score = frame.get("quality_score")
                    if q_score is not None and q_score <= 0.0:
                        continue

                    rel_path = frame.get("path")
                    if rel_path and not rel_path.startswith(("http", "gs://")):
                        abs_path = self.media_root / rel_path
                        if abs_path.exists():
                            # 2. Digest Filter: 基于内容摘要去重
                            digest = frame.get("digest")
                            if digest:
                                if digest in seen_digests:
                                    continue
                                seen_digests.add(digest)

                            files_to_upload.append(str(abs_path))

        files_to_upload = list(set(files_to_upload))

        return {"files_to_upload": files_to_upload, "asset_id": asset_id, "material_id": str(target.id)}

    def _handle_sync(self, target, result):
        mapping: Dict[str, str] = result.get("mapping", {})
        if not mapping or not target.keyframe_map:
            return

        # 1. 构建 Digest -> Cloud URL 的映射 (广播源)
        # 因为上传时进行了去重，我们需要通过已上传的文件路径反查其 Digest
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

                # 优先尝试通过 Digest 广播更新 (处理冗余帧)
                if digest and digest in digest_to_url:
                    frame["path"] = digest_to_url[digest]
                elif rel_path:
                    # Fallback: 尝试通过 Path 更新
                    abs_path = str(self.media_root / rel_path)
                    if abs_path in mapping:
                        frame["path"] = mapping[abs_path]

        # 确保回写的是 FrameDataInput
        processed_map = {
            slice_id: [FrameDataInput(**frame_data).model_dump() for frame_data in frames]
            for slice_id, frames in updated_keyframe_map.items()
        }
        target.keyframe_map = processed_map

    def _check_sync_ready(self, target):
        # Sync 依赖 keyframe_map
        return bool(target.keyframe_map) and any(bool(v) for v in target.keyframe_map.values())

    def _check_sync_done(self, target):
        if not target.keyframe_map:
            return False
        # 检查 keyframe_map 中是否有任何一个帧的 path 已经变为云端地址
        for slice_id, frames in target.keyframe_map.items():
            for frame in frames:
                if frame.get("path", "").startswith(("http", "gs://")):
                    return True
        return False
