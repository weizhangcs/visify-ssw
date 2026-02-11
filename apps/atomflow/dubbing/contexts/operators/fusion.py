class AudioVisualFusionContextMixin:
    def _payload_audio_visual_fusion(self, target):
        # [Optimization] 切换到精修后的脚本作为 Fusion 输入
        # 这样可以利用 OCR 召回的内容，并基于更准确的时间轴进行说话人匹配
        raw_script = target.script_refinement_meta.get("refined_script", [])

        # 过滤掉被标记为噪音的片段，避免对无效内容进行计算
        metadata = [seg for seg in raw_script if seg.get("source_of_truth") != "DISCARD_NOISE"]

        return {
            "metadata": metadata,
            "face_csv_path": str(self.media_root / target.face_csv_path),
            "audio_path": str(self.media_root / target.track_perception),
        }

    def _handle_audio_visual_fusion(self, target, result):
        target.fused_metadata = result

    def _check_audio_visual_fusion_ready(self, target):
        # 依赖：Script Refinement (meta), Visual (face_csv), Perception Track (audio)
        return bool(target.script_refinement_meta and target.face_csv_path and target.track_perception)

    def _check_audio_visual_fusion_done(self, target):
        return bool(target.fused_metadata)
