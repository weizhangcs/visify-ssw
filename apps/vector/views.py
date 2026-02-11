import json
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from apps.media_assets.models import Media

from .models import VectorSourceAsset
from .services.embedding import EmbeddingService
from .services.storage import VectorStorageService


@login_required
def vector_search_view(request):
    """
    [Lab] 向量检索实验室
    提供一个简单的界面，用于测试和验证向量索引的召回效果。
    """
    # 获取所有资产用于下拉选择
    assets_qs = VectorSourceAsset.objects.all().order_by("-created").values("id", "title")
    # [Fix] Serialize UUID to string and dump to JSON to avoid "UUID is not defined" in JS
    assets_list = [{"id": str(a["id"]), "title": a["title"]} for a in assets_qs]

    context = {
        **admin.site.each_context(request),  # [Fix] 注入 Admin 上下文以显示侧边栏
        "assets": json.dumps(assets_list, ensure_ascii=False),
        "title": "向量检索实验室",
    }
    return render(request, "vector/search.html", context)


@csrf_exempt
@login_required
def vector_search_api(request):
    """
    [API] 执行向量检索并返回水合后的结果
    """
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        asset_id = data.get("asset_id")
        query = data.get("query")
        index_types = data.get("index_types", ["dialogue"])  # List[str]
        top_k = int(data.get("top_k", 10))

        if not asset_id or not query:
            return JsonResponse({"status": "error", "message": "Missing asset_id or query"}, status=400)

        # 1. 编码查询 (E5 模型需要 'query: ' 前缀)
        query_text = f"query: {query}"
        query_vector = EmbeddingService.encode(query_text)

        all_results = []

        # 2. 并发/循环检索所有选定的索引类型
        for idx_type in index_types:
            index_path = Path(settings.MEDIA_ROOT) / "vector_indices" / asset_id / f"{idx_type}.index"
            if index_path.exists():
                # 稍微放大检索量，以便合并后排序截断
                type_results = VectorStorageService.load_and_search(index_path, query_vector, top_k=top_k)
                # 注入类型标识
                for r in type_results:
                    r["type"] = idx_type
                all_results.extend(type_results)

        # 3. 合并排序并截断
        # 按分数降序 (分数越高越相似)
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        final_results = all_results[:top_k]

        # 4. 结果水合 (Hydration) - 注入 URL
        # 收集涉及的 sequence numbers
        seqs = set(r.get("seq", 1) for r in final_results)

        # 批量查询 Media 信息
        medias = Media.objects.filter(asset_id=asset_id, sequence_number__in=seqs).select_related("material")
        media_map = {m.sequence_number: m for m in medias}

        hydrated_results = []
        for item in final_results:
            seq = item.get("seq", 1)
            media = media_map.get(seq)

            if media:
                # 基础信息
                item["media_title"] = media.title
                item["video_url"] = media.get_best_playback_url()

                # 针对 Frame 类型，查找图片 URL
                if item["type"] == "frame":
                    # 从 Material.frames 中查找对应 ID 的路径
                    # 注意：这可能在数据量极大时有性能损耗，但在 Lab 场景下可接受
                    if hasattr(media, "material"):
                        frames = media.material.frames or []
                        target_frame = next((f for f in frames if f.get("id") == item["id"]), None)
                        if target_frame and target_frame.get("path"):
                            # [Fix] 强制转换云端路径 (gs://) 为本地 Refinery 路径
                            # 原始路径可能已被 Synchronize 任务更新为 gs://...，导致 Nginx 无法访问
                            # 本地路径规则: refinery/{material_id}/frames/{filename}
                            cloud_path = target_frame["path"]
                            filename = Path(cloud_path).name
                            local_rel_path = f"refinery/{media.material.id}/frames/{filename}"

                            # 转换相对路径为绝对 URL (自动添加 /media/ 前缀)
                            item["image_url"] = media.ensure_absolute_url(local_rel_path)

            hydrated_results.append(item)

        return JsonResponse({"status": "success", "data": hydrated_results})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
