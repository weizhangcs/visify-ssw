import logging
import pickle
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings

from apps.common.schemas.narrative_dataset import NarrativeDataset

logger = logging.getLogger(__name__)

# 尝试导入 ML 依赖，允许在非 GPU/推理环境下运行 Django
try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
except ImportError:
    faiss = None
    np = None
    SentenceTransformer = None


class ProjectRAGService:
    """
    [Inference Layer] 本地 RAG 引擎服务

    职责：
    1. 消费 Annotation Workbench 产出的 NarrativeDataset (Blueprint)。
    2. 构建基于场景 (Scene) 粒度的本地向量索引。
    3. 提供语义检索能力，供 Creative 模块调用。
    """

    # 使用轻量级多语言模型，平衡速度与精度
    MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

    # 索引存储根目录
    INDEX_ROOT = Path(settings.MEDIA_ROOT) / "inference" / "rag_indices"

    @classmethod
    def _get_model_path(cls) -> str:
        """获取模型路径，优先使用 Docker 预置的离线模型"""
        offline_path = Path("/app/local_models") / cls.MODEL_NAME
        if offline_path.exists():
            return str(offline_path)
        return cls.MODEL_NAME

    @classmethod
    def get_index_path(cls, project_id: str) -> Path:
        """获取指定项目的索引文件路径"""
        return cls.INDEX_ROOT / str(project_id) / "scene_index.pkl"

    @classmethod
    def build_index(cls, project_id: str, dataset: NarrativeDataset) -> str:
        """
        [核心构建] 将 NarrativeDataset 构建为向量索引

        Args:
            project_id: 项目 UUID
            dataset: 标注完成后的数据集对象

        Returns:
            索引文件的绝对路径
        """
        if not faiss or not SentenceTransformer:
            raise RuntimeError("RAGService: 缺少 faiss-cpu 或 sentence-transformers 依赖")

        logger.info(f"[RAG] Starting index build for Project {project_id}...")

        # 1. 数据预处理：将 Scene 转换为文档 (Document)
        documents = []
        metadata_list = []

        # NarrativeDataset.scenes 是一个 Dict[uuid, Scene]
        scenes = dataset.scenes.values() if isinstance(dataset.scenes, dict) else dataset.scenes

        for scene in scenes:
            # 确保是对象而不是字典 (Pydantic 兼容性)
            if isinstance(scene, dict):
                # 简单处理，如果上游传的是 dict
                s_id = scene.get("id")
                s_uuid = scene.get("scene_uuid")
                narrative = scene.get("narrative_summary", "")
                dialogues = scene.get("dialogues", [])
                highlights = scene.get("highlights", [])
                mood = scene.get("mood_and_atmosphere", "")
                location = scene.get("inferred_location", "")
            else:
                # [Fix] 兼容 Pydantic 字段别名 (JSON中的 'id' 可能对应模型中的 'local_id' 或 'scene_id')
                s_id = getattr(scene, "id", getattr(scene, "local_id", getattr(scene, "scene_id", 0)))
                s_uuid = scene.scene_uuid
                narrative = scene.narrative_summary
                dialogues = scene.dialogues
                highlights = scene.highlights
                mood = scene.mood_and_atmosphere
                location = scene.inferred_location

            # --- 文本构造策略 (Prompt Engineering for Embedding) ---
            # 目标：让语义向量尽可能包含 剧情、对白、氛围 三个维度的信息

            text_parts = []

            # A. 核心剧情
            if narrative:
                text_parts.append(f"Plot: {narrative}")

            # B. 环境与氛围
            env_info = []
            if location and location != "Unknown":
                env_info.append(location)
            if mood:
                env_info.append(mood)
            if env_info:
                text_parts.append(f"Atmosphere: {', '.join(env_info)}")

            # C. 关键对白 (截取前N句或全部，视长度而定，这里全量放入但限制单句长度)
            if dialogues:
                dial_text = " ".join([f"{d.speaker}: {d.content}" for d in dialogues])
                # 简单的截断防止 token 溢出 (MiniLM 上限通常 512 tokens，约 1000 chars)
                if len(dial_text) > 800:
                    dial_text = dial_text[:800] + "..."
                text_parts.append(f"Dialogues: {dial_text}")

            # D. 高光描述
            if highlights:
                hl_text = " ".join([h.description for h in highlights if h.description])
                if hl_text:
                    text_parts.append(f"Highlights: {hl_text}")

            full_text = "\n".join(text_parts)

            documents.append(full_text)
            metadata_list.append(
                {
                    "scene_local_id": s_id,
                    "scene_uuid": str(s_uuid),
                    "start_time": getattr(scene, "start_time", ""),
                    "end_time": getattr(scene, "end_time", ""),
                    "raw_text": full_text,  # [Optimization] 保留全量文本，用于 RAG 上下文构建和调试
                }
            )

        if not documents:
            logger.warning(f"[RAG] No scenes found in dataset for Project {project_id}.")
            return ""

        # 2. Embedding
        model = SentenceTransformer(cls._get_model_path())
        embeddings = model.encode(documents, convert_to_numpy=True, show_progress_bar=False)
        faiss.normalize_L2(embeddings)

        # 3. 构建索引 (Inner Product for Cosine Similarity)
        d = embeddings.shape[1]
        index = faiss.IndexFlatIP(d)
        index.add(embeddings)

        # 4. 序列化保存
        output_path = cls.get_index_path(project_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data_to_save = {"metadata": metadata_list, "faiss_index": faiss.serialize_index(index)}

        with open(output_path, "wb") as f:
            pickle.dump(data_to_save, f)

        logger.info(f"[RAG] Index saved to {output_path} ({index.ntotal} scenes)")
        return str(output_path)

    @classmethod
    def search(cls, project_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        [检索] 在指定项目中搜索相关场景
        """
        index_path = cls.get_index_path(project_id)
        if not index_path.exists():
            logger.warning(f"[RAG] Index not found for Project {project_id}")
            return []

        with open(index_path, "rb") as f:
            data = pickle.load(f)

        index = faiss.deserialize_index(data["faiss_index"])
        metadata = data["metadata"]

        model = SentenceTransformer(cls._get_model_path())
        query_vec = model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_vec)

        distances, indices = index.search(query_vec, top_k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            item = metadata[idx].copy()
            item["score"] = float(distances[0][i])
            results.append(item)

        return results
