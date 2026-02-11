class AudioVisualFusionContextMixin:
    def _payload_audio_visual_fusion(self, target):
        # 从 perception_meta 中提取 metadata 列表
        metadata = target.perception_meta.get("metadata", [])
        return {
            "metadata": metadata,
            "face_csv_path": str(self.media_root / target.face_csv_path),
            "audio_path": str(self.media_root / target.track_perception),
        }

    def _handle_audio_visual_fusion(self, target, result):
        target.fused_metadata = result

    def _check_audio_visual_fusion_ready(self, target):
        # 依赖：Perception (metadata), Visual (face_csv), Perception Track (audio)
        return bool(target.perception_meta and target.face_csv_path and target.track_perception)

    def _check_audio_visual_fusion_done(self, target):
        return bool(target.fused_metadata)
