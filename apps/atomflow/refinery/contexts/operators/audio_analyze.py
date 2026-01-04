class AudioAnalyzeContextMixin:
    def _payload_audio_analyze(self, target):
        proxy_rel = target.proxy_video
        abs_proxy_path = self.media_root / proxy_rel

        return {
            "video_path": str(abs_proxy_path),
            "dialogue_track": target.dialogue_track,
        }

    def _handle_audio_analyze(self, target, result):
        target.dialogue_track = result.get("dialogue_track", [])

    def _check_audio_analyze_ready(self, target):
        return bool(target.proxy_video) and bool(target.dialogue_track)

    def _check_audio_analyze_done(self, target):
        if not target.dialogue_track:
            return False
        # Check if at least one item has audio_analysis
        return any(item.get("audio_analysis") for item in target.dialogue_track)
