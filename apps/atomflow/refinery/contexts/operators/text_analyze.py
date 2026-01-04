class TextAnalyzeContextMixin:
    """
    Context Mixin for text analysis (subtitle processing).

    Provides methods to generate payloads for and handle results from the TextAnalyzerService.
    """

    def _payload_text_analyze(self, target):
        """
        Generate payload for the TextAnalyzerService.

        Reads the source subtitle file content and determines the language.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the subtitle content and language code.
        """
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
        """
        Handle the result from the TextAnalyzerService.

        Updates the Material's dialogue_track with the analyzed subtitle items.

        Args:
            target: The Material instance.
            result: A dictionary containing the 'dialogue_track' list.
        """
        target.dialogue_track = result.get("dialogue_track", [])

    def _check_text_analyze_ready(self, target):
        """
        Check if the Text Analyze task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True (always ready if source subtitle exists, handled in payload generation).
        """
        return True

    def _check_text_analyze_done(self, target):
        """
        Check if the Text Analyze task has already been completed.

        Args:
            target: The Material instance.

        Returns:
            True if dialogue_track is populated, False otherwise.
        """
        return bool(target.dialogue_track)
