class CharacterRefineContextMixin:
    """
    Context Mixin for character refinement via Cloud LLM.

    Provides methods to generate payloads for and handle results from the CharacterRefinerService.
    """

    def _payload_character_refine(self, target):
        """
        Generate payload for the CharacterRefinerService.

        Args:
            target: The Material instance.

        Returns:
            A dictionary containing the dialogue and asset metadata.
        """
        asset = getattr(target.media, "asset", None)
        lang = "zh"
        if asset and asset.language:
            lang = asset.language.split("-")[0]

        return {
            "dialogue": target.dialogue,
            "video_title": target.media.title,
            "known_characters": asset.known_characters if asset else [],
            "lang": lang,
        }

    def _handle_character_refine(self, target, result):
        """
        Handle the result from the CharacterRefinerService.

        Merges the incremental updates (speaker, reasoning) from the result
        into the existing dialogue.

        Args:
            target: The Material instance.
            result: A dictionary containing a list of 'updates' (mapped from identified_subtitles).
        """
        updates = result.get("updates", [])
        original_track = target.dialogue

        # Create a map for efficient lookups
        updates_map = {u.get("index"): u for u in updates if "index" in u}

        merged_track = []
        for item in original_track:
            new_item = item.copy()
            idx = new_item.get("index")

            if idx in updates_map:
                update_data = updates_map[idx]
                if "speaker" in update_data:
                    new_item["speaker"] = update_data["speaker"]
                if "reasoning" in update_data:
                    new_item["reasoning"] = update_data["reasoning"]

            merged_track.append(new_item)

        target.dialogue = merged_track

    def _check_character_refine_ready(self, target):
        """
        Check if the Character Refine task is ready to run.

        Args:
            target: The Material instance.

        Returns:
            True if the dialogue is populated, False otherwise.
        """
        return bool(target.dialogue)

    def _check_character_refine_done(self, target):
        """
        Check if the Character Refine task has already been completed.

        This check relies on the Pipeline's metrics, as it's difficult to
        determine completion status from the data alone (e.g., 'Unknown'
        could be a valid result).

        Args:
            target: The Material instance.

        Returns:
            True if the pipeline metrics show a successful run for this slug.
        """
        pipeline = self.pipeline
        if not pipeline or not pipeline.metrics:
            return False
        for seq, data in pipeline.metrics.items():
            if data.get("slug") == "character_refine" and data.get("status") == "SUCCESS":
                return True
        return False
