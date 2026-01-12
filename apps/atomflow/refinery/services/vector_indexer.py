import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List

try:
    import faiss
    from sentence_transformers import SentenceTransformer
except ImportError:
    faiss = None
    SentenceTransformer = None

logger = logging.getLogger(__name__)


class VectorIndexerService:
    """
    [Refinery Operator] 本地向量索引构建服务。

    职责：
    1. 将 Material 中的 Slices 转化为富语义文本 (Visual + Narrative + Tags)。
    2. 使用多语言模型生成 Embedding。
    3. 构建 FAISS 索引并序列化存储到本地 (.pkl)。
    """

    # 使用经过验证的多语言模型
    MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

    @classmethod
    def _get_model_path_or_name(cls) -> str:
        """
        获取模型加载路径。优先使用 Docker 镜像内预置的离线模型。
        """
        # Dockerfile 中 COPY 进去的路径
        offline_path = Path("/app/local_models") / cls.MODEL_NAME
        if offline_path.exists():
            return str(offline_path)
        return cls.MODEL_NAME

    @staticmethod
    def run(slices: List[Dict[str, Any]], output_path: Path) -> str:
        """
        执行索引构建。

        Args:
            slices: 切片数据列表 (Material.slices)。
            output_path: 索引文件输出绝对路径 (.pkl)。

        Returns:
            生成的索引文件相对路径 (用于回填数据库，这里返回 str(output_path) 供 Context 处理)。
        """
        if not slices:
            logger.warning("VectorIndex: No slices provided, skipping index generation.")
            return ""

        if faiss is None or SentenceTransformer is None:
            raise RuntimeError("VectorIndexService: 缺少 faiss-cpu 或 sentence-transformers 依赖")

        logger.info(f"VectorIndex: Starting indexing for {len(slices)} slices...")

        # 1. 文本化 (Textification)
        corpus = []
        metadata = []  # 存储 slice_id 和时长，用于检索后回溯

        for s in slices:
            # 组合视觉摘要、叙事动作、标签
            # 权重策略：视觉摘要(画面) > 叙事摘要(剧情) > 标签(氛围)
            text_parts = []

            analysis = s.get("slice_analysis") or {}

            if analysis.get("visual_summary"):
                # [优化] 移除 "Visual:" 前缀，让模型直接理解自然语言，减少 Token 噪声
                text_parts.append(f"{analysis['visual_summary']}")

            if analysis.get("narrative_summary"):
                text_parts.append(f"Narrative: {analysis['narrative_summary']}")

            tags = analysis.get("tags", [])
            if tags:
                text_parts.append(f"Tags: {', '.join(tags)}")

            # [新增] 包含切片内的对白文本 (扁平化处理)
            # 业务价值：解说词往往会呼应视频里的台词 (e.g. "正如他所说...")
            text_contents = s.get("text_contents", [])
            if text_contents:
                dialogue_text = " ".join([t.get("content", "") for t in text_contents if t.get("content")])
                if dialogue_text:
                    text_parts.append(f"Dialogue: {dialogue_text}")

            # 兜底：如果分析为空，使用空字符串占位，保证索引对齐
            full_text = " | ".join(text_parts) if text_parts else "Unanalyzed content"
            corpus.append(full_text)

            metadata.append(
                {
                    "slice_id": s.get("slice_id"),
                    "start_time": s.get("start_time"),
                    "end_time": s.get("end_time"),
                    "duration": s.get("end_time", 0) - s.get("start_time", 0),
                }
            )

        # [Debug] 核心调试：输出扁平化后的语料文本
        # 这让开发者能直观看到“到底是什么内容被变成了向量”
        debug_path = output_path.parent / "index_corpus_debug.txt"
        try:
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(f"Total Slices: {len(corpus)}\n")
                f.write("=" * 60 + "\n\n")
                for i, text in enumerate(corpus):
                    meta = metadata[i]
                    f.write(
                        f"[Slice ID: {meta['slice_id']}] (Time: {meta['start_time']:.2f}-{meta['end_time']:.2f}s)\n"  # noqa: E231,E501
                    )
                    f.write(f"Flattened Text: {text}\n")
                    f.write("-" * 30 + "\n")
            logger.info(f"VectorIndex: Saved debug corpus to {debug_path}")
        except Exception as e:
            logger.warning(f"VectorIndex: Failed to write debug corpus: {e}")

        # 2. Embedding
        model_source = VectorIndexerService._get_model_path_or_name()
        model = SentenceTransformer(model_source)
        embeddings = model.encode(corpus, convert_to_numpy=True, show_progress_bar=False)

        # 归一化以支持余弦相似度 (FAISS Inner Product)
        faiss.normalize_L2(embeddings)

        # 3. 构建索引
        d = embeddings.shape[1]
        index = faiss.IndexFlatIP(d)
        index.add(embeddings)

        # 4. 序列化保存 (Index + Metadata)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data_to_save = {"metadata": metadata, "faiss_index": faiss.serialize_index(index)}  # 序列化 C++ 对象

        with open(output_path, "wb") as f:
            pickle.dump(data_to_save, f)

        logger.info(f"VectorIndex: Saved index to {output_path} ({index.ntotal} vectors)")
        return str(output_path)
