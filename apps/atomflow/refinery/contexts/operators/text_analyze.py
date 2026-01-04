class TextAnalyzeContextMixin:
    def _payload_text_analyze(self, target):
        src_sub = getattr(target.media, "source_subtitle", None)
        rel_path = src_sub.name if hasattr(src_sub, "name") else src_sub

        content = ""
        if rel_path:
            abs_path = self.media_root / rel_path
            if abs_path.exists():
                try:
                    content = abs_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    content = abs_path.read_text(encoding="gb18030", errors="ignore")

        asset = getattr(target.media, "asset", None)
        lang = "zh"
        if asset and asset.language:
            lang = asset.language.split("-")[0]

        return {"content": content, "lang": lang}

    def _handle_text_analyze(self, target, result):
        target.dialogue_track = result.get("dialogue_track", [])

    def _check_text_analyze_ready(self, target):
        return True

    def _check_text_analyze_done(self, target):
        return bool(target.dialogue_track)
