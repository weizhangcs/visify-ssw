class CharacterRefineContextMixin:
    def _payload_character_refine(self, target):
        asset = getattr(target.media, "asset", None)
        lang = "zh"
        if asset and asset.language:
            lang = asset.language.split("_")[0]

        return {
            "dialogue_track": target.dialogue_track,
            "video_title": target.media.title,
            "known_characters": asset.known_characters if asset else [],
            "lang": lang,
        }

    def _handle_character_refine(self, target, result):
        updates = result.get("updates", [])
        original_track = target.dialogue_track

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

        target.dialogue_track = merged_track

    def _check_character_refine_ready(self, target):
        return bool(target.dialogue_track)

    def _check_character_refine_done(self, target):
        pipeline = self.pipeline
        if not pipeline or not pipeline.metrics:
            return False
        for seq, data in pipeline.metrics.items():
            if data.get("slug") == "character_refine" and data.get("status") == "SUCCESS":
                return True
        return False
