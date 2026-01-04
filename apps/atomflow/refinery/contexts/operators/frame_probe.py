from ...schemas import FrameDataInput


class FrameProbeContextMixin:
    def _payload_frame_probe(self, target):
        # 帧探测需要 keyframe_map
        return {"keyframe_map": target.keyframe_map, "media_root": str(self.media_root)}

    def _handle_frame_probe(self, target, result: dict):
        # result 现在是更新后的 keyframe_map
        # 确保 keyframe_map 存储的是 FrameDataInput
        # 通过全量替换，天然支持了冗余数据的回写
        processed_map = {
            slice_id: [FrameDataInput(**frame_data).model_dump() for frame_data in frames]
            for slice_id, frames in result.items()
        }
        target.keyframe_map = processed_map

    def _check_frame_probe_ready(self, target):
        # 帧探测依赖于帧抽取完成
        return bool(target.keyframe_map) and any(bool(v) for v in target.keyframe_map.values())

    def _check_frame_probe_done(self, target):
        # 检查至少有一个切片的帧数据中包含了 quality_score
        if not target.keyframe_map:
            return False
        for slice_id, frames in target.keyframe_map.items():
            for frame in frames:
                if frame.get("quality_score") is not None:
                    return True
        return False
