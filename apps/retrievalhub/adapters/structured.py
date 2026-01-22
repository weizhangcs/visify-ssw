import logging
from typing import Any, Dict, List

from apps.common.schemas.dataset.schemas import Scene, SubtitleItem
from apps.media_assets.models import Media
from apps.retrievalhub.schemas import RetrievalResult
from apps.workflow.annotation.jobs import AnnotationJob

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class StructuredAdapter(BaseAdapter):
    """
    结构化数据适配器。
    直接查询 AnnotationJob 的 JSON 产出 (Dialogues, Scenes 等)。
    适用于精确过滤、关键词匹配等非向量场景。
    """

    def search(self, query: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        asset_id = context.get("asset_id")
        if not asset_id:
            return []

        # 简单实现：如果 query 为空，或者显式指定了 filters，则执行逻辑
        # 这里演示基于简单的文本包含匹配，实际可扩展为 JSONPath 或 SQL 查询

        # 获取该 Asset 下所有 Media 的最新 AnnotationJob
        medias = Media.objects.filter(asset_id=asset_id).order_by("sequence_number")
        results = []

        for media in medias:
            job = AnnotationJob.objects.filter(media=media).last()
            if not job or job.status != "COMPLETED":
                continue

            # 搜索 Dialogues
            if "dialogue" in context.get("index_types", ["dialogue"]):
                for d in job.dialogues or []:
                    if self._match(query, d.get("content", "")):
                        item_obj = SubtitleItem(**d)
                        results.append(self._wrap_result(item_obj, "dialogue", media, score=1.0))

            # 搜索 Scenes
            if "scene" in context.get("index_types", ["scene"]):
                for s in job.scenes or []:
                    content = s.get("content", {})
                    # 搜索剧情或地点
                    text = f"{content.get('narrative_action', '')} {content.get('location', '')}"
                    if self._match(query, text):
                        item_obj = Scene(**s)
                        results.append(self._wrap_result(item_obj, "scene", media, score=1.0))

        return results

    def _match(self, query: str, text: str) -> bool:
        """简单的不区分大小写包含匹配"""
        if not query:
            return True
        return query.lower() in text.lower()

    def _wrap_result(self, domain_obj: Any, item_type: str, media: Media, score: float) -> RetrievalResult:
        """封装为统一的 RetrievalResult"""
        return RetrievalResult(
            score=score,
            source="structured",
            type=item_type,
            content=domain_obj,
            media_id=str(media.id),
            media_title=media.title,
            video_url=media.get_best_playback_url(),
        )
