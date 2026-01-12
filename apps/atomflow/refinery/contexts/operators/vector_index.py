from pathlib import Path


class VectorIndexContextMixin:
    """
    Context Mixin for local vector indexing.
    """

    @property
    def media_root(self) -> Path:
        raise NotImplementedError

    def _payload_vector_index(self, target):
        """
        Generate payload for VectorIndexService.
        """
        # 定义输出路径: media_root/refinery/<id>/index.pkl
        rel_path = f"refinery/{target.id}/index.pkl"
        abs_output_path = self.media_root / rel_path

        return {"slices": target.slices, "output_path": str(abs_output_path), "rel_path": rel_path}

    def _handle_vector_index(self, target, result):
        """
        Handle result: Update Material.local_vector_index_path.
        """
        target.slice_vector_index_path = result.get("rel_path")

    def _check_vector_index_ready(self, target):
        """
        Ready if slices exist.
        Ideally, this should run AFTER SliceAnalyzer to ensure semantic data exists.
        """
        if not target.slices:
            return False
        # 检查是否包含 slice_analysis (确保有内容可索引)
        return any(s.get("slice_analysis") for s in target.slices)

    def _check_vector_index_done(self, target):
        """
        Done if local_vector_index_path is populated.
        """
        return bool(target.slice_vector_index_path)
