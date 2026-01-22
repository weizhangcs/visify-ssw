from pathlib import Path

from apps.common.schemas.dataset.schemas import KeyframeItem


class FrameProbeContextMixin:
    """
    Context Mixin for frame probing (quality assessment).

    Provides methods to generate payloads for and handle results from the FrameProbeService.
    """

    @property
    def media_root(self) -> Path:
        raise NotImplementedError

    def _payload_frame_probe(self, target):
        """
        Generate payload for the FrameProbeService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the keyframe_map and the media root path.
        """
        # Frame probe requires the keyframe_map to access frame paths
        return {"keyframe_map": target.keyframe_map, "media_root": str(self.media_root)}

    def _handle_frame_probe(self, target, result: dict):
        """
        Handle the result from the FrameProbeService.

        Updates the Material's keyframe_map with quality scores and filter reasons.
        [Phase 1 Enhanced]
        1. Filters out invalid frames (score <= 0).
        2. Back-populates valid frame IDs to Material.slices.

        Args:
         target: The Material instance.
         result: The updated keyframe_map dictionary.
        """
        filtered_map = {}
        valid_frames_flat = []

        # 1. 过滤无效帧 & 展平 (Filter & Flatten)
        for slice_id, frames in result.items():
            valid_slice_frames = []
            for frame_data in frames:
                # 质量校验: 仅保留正分数的帧
                # FrameProbeService 通常将模糊/黑屏帧的分数置为 0.0 或 None
                q_score = frame_data.get("quality_score", 0.0)

                if q_score is not None and q_score > 0:
                    # 校验并序列化
                    item = KeyframeItem(**frame_data).model_dump()
                    valid_slice_frames.append(item)
                    valid_frames_flat.append(item)

            # 仅保留包含有效帧的切片记录
            if valid_slice_frames:
                filtered_map[slice_id] = valid_slice_frames

        # 2. 更新 Material 视觉资产 (SSOT)
        target.keyframe_map = filtered_map

        target.frames = valid_frames_flat

        # 3. 双向索引回写 (Back-populate frame_ids to Slices)
        # 构建 Slice UUID -> [Frame UUIDs] 的映射
        slice_frame_ref = {s_id: [f["id"] for f in fs] for s_id, fs in filtered_map.items()}

        # 遍历并更新 Slices (In-place update)
        updated_slices = []
        for s_data in target.slices:
            s_id = s_data.get("id")
            # 如果该切片有有效帧，则回填 ID；否则置空
            s_data["frame_ids"] = slice_frame_ref.get(s_id, [])
            updated_slices.append(s_data)

        target.slices = updated_slices

    def _check_frame_probe_ready(self, target):
        """
        Check if the Frame Probe task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if keyframe_map is populated, False otherwise.
        """
        # Frame probe depends on frame extraction completion
        return bool(target.keyframe_map) and any(bool(v) for v in target.keyframe_map.values())

    def _check_frame_probe_done(self, target):
        """
        Check if the Frame Probe task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if at least one frame has a quality score, False otherwise.
        """
        if not target.keyframe_map:
            return False
        for slice_id, frames in target.keyframe_map.items():
            for frame in frames:
                if frame.get("quality_score") is not None:
                    return True
        return False
