import logging
from pathlib import Path
from typing import Any, Dict, List

from django.conf import settings

from apps.atomflow.refinery.schemas import KeyframeItem, Scene, SubtitleItem
from apps.media_assets.models import Media
from apps.retrievalhub.schemas import RetrievalResult
from apps.vector.services.embedding import EmbeddingService
from apps.vector.services.storage import VectorStorageService
from apps.workflow.annotation.jobs import AnnotationJob

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class VectorAdapter(BaseAdapter):
    """
    向量检索适配器。
    负责调用 apps.vector 提供的基础设施进行语义检索，并注入业务实体信息（Media）。
    """

    def search(self, query: str, context: Dict[str, Any]) -> List[RetrievalResult]:
        asset_id = context.get("asset_id")
        if not asset_id:
            logger.warning("VectorAdapter: Missing asset_id in context")
            return []

        # 1. 参数解析
        index_types = context.get("index_types", ["dialogue", "scene", "slice", "frame"])
        top_k = context.get("top_k", 10)

        # 2. 语义向量化 (Infrastructure Layer)
        # E5 模型建议 Query 添加前缀
        query_text = f"query: {query}"
        try:
            query_vector = EmbeddingService.encode(query_text)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return []

        all_results = []

        # 3. 多路召回 (Infrastructure Layer)
        base_path = Path(settings.MEDIA_ROOT) / "vector_indices" / str(asset_id)

        for idx_type in index_types:
            index_path = base_path / f"{idx_type}.index"
            if not index_path.exists():
                continue

            try:
                # 稍微放大单路检索量，以便后续融合
                raw_results = VectorStorageService.load_and_search(index_path, query_vector, top_k=top_k)
                for r in raw_results:
                    r["type"] = idx_type  # 注入来源类型
                    r["source"] = "vector"
                all_results.extend(raw_results)
            except Exception as e:
                logger.error(f"Search failed for index {index_path}: {e}")

        # 4. 排序截断
        # 按相似度分数降序
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        final_results = all_results[:top_k]

        # 5. 结果水合 (Hydration) - 注入业务实体信息
        return self._hydrate_results(asset_id, final_results)

    def _hydrate_results(self, asset_id: str, results: List[Dict]) -> List[RetrievalResult]:
        """
        深度水合：
        1. 关联 Media 信息。
        2. 回查 AnnotationJob/Material 获取完整的 Pydantic 领域对象。
        """
        if not results:
            return []

        # 1. 批量获取 Media
        seqs = set(r.get("seq", 1) for r in results)
        medias = Media.objects.filter(asset_id=asset_id, sequence_number__in=seqs).select_related("material")
        media_map = {m.sequence_number: m for m in medias}

        # 2. 批量获取 AnnotationJob (用于 Dialogue/Scene/Slice)
        # 策略：获取这些 Media 下最新的 Completed Job
        jobs = AnnotationJob.objects.filter(media__in=medias, status="COMPLETED").order_by("media_id", "-created_at")

        # 构建数据查找表: media_id -> type -> id -> item_dict
        data_lookup = {}
        for job in jobs:
            if job.media_id in data_lookup:
                continue  # 已获取最新

            data_lookup[job.media_id] = {
                "dialogue": {d["id"]: d for d in (job.dialogues or [])},
                "scene": {s["id"]: s for s in (job.scenes or [])},
                # 如果 Job 中包含 slice 信息也可在此索引
            }

        hydrated = []
        for item in results:
            seq = item.get("seq", 1)
            item_id = item.get("id")
            item_type = item.get("type")
            media = media_map.get(seq)

            if not media:
                continue

            domain_object = None
            image_url = None

            # A. 处理 Frame (数据源在 Material)
            if item_type == "frame":
                if hasattr(media, "material") and media.material.frames:
                    frame_dict = next((f for f in media.material.frames if f.get("id") == item_id), None)
                    if frame_dict:
                        domain_object = KeyframeItem(**frame_dict)
                        image_url = self._resolve_frame_url(media, frame_dict)

            # B. 处理 Dialogue/Scene (数据源在 AnnotationJob)
            elif item_type in ["dialogue", "scene"]:
                media_data = data_lookup.get(media.id, {})
                type_data = media_data.get(item_type, {})
                obj_dict = type_data.get(item_id)

                if obj_dict:
                    if item_type == "dialogue":
                        domain_object = SubtitleItem(**obj_dict)
                    elif item_type == "scene":
                        domain_object = Scene(**obj_dict)

            if domain_object:
                hydrated.append(
                    RetrievalResult(
                        score=item.get("score", 0),
                        source="vector",
                        type=item_type,
                        content=domain_object,
                        media_id=str(media.id),
                        media_title=media.title,
                        video_url=media.get_best_playback_url(),
                        image_url=image_url,
                    )
                )

        return hydrated

    def _resolve_frame_url(self, media: Media, frame_dict: Dict) -> str:
        """解析帧图片 URL"""
        if frame_dict.get("path"):
            cloud_path = frame_dict["path"]
            # 逻辑复用自原 views.py: 将 gs:// 路径转换为本地 Refinery 相对路径
            # 假设文件名保持一致
            filename = Path(cloud_path).name
            local_rel_path = f"refinery/{media.material.id}/frames/{filename}"

            # 转换为绝对 URL
            return media.ensure_absolute_url(local_rel_path)

        return ""
