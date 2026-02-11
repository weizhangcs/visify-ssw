# 文件路径: apps/vector/admin.py

from django.contrib import admin
from unfold.admin import ModelAdmin

from ..workflow.annotation.jobs import AnnotationJob
from .models import VectorIndex, VectorSourceAsset
from .services.indexer import VectorIndexerService


@admin.register(VectorIndex)
class VectorIndexAdmin(ModelAdmin):
    list_display = ("asset_title", "index_type", "vector_count", "dimension", "is_active", "modified")
    list_filter = ("index_type", "is_active", "model_name")
    search_fields = ("target_id",)
    readonly_fields = ("target_id", "index_type", "file_path", "vector_count", "dimension", "model_name")

    @admin.display(description="资产标题")
    def asset_title(self, obj):
        try:
            return VectorSourceAsset.objects.get(pk=obj.target_id).title
        except Exception:
            return obj.target_id


@admin.register(VectorSourceAsset)
class VectorSourceAssetAdmin(ModelAdmin):
    """
    [Asset-Centric] 资产级向量索引管理。
    支持将 Asset 下的所有 Media 聚合为一个大的向量库，并注入 sequence 维度。
    """

    list_display = ("title", "media_count", "annotation_status", "created")
    search_fields = ("title", "id")
    actions = ["build_asset_index_action"]

    # [Fix] 禁止在此处创建/删除/修改资产，仅作为只读视图用于触发索引构建
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="媒体数量")
    def media_count(self, obj):
        return obj.medias.count()

    @admin.display(description="标注状态")
    def annotation_status(self, obj):
        total = obj.medias.count()
        if total == 0:
            return "无媒体"

        completed_count = 0
        for media in obj.medias.all():
            job = AnnotationJob.objects.filter(media=media).last()
            if job and job.status == "COMPLETED":
                completed_count += 1

        if completed_count == total:
            return "✅ 已完成"
        elif completed_count == 0:
            return "⏳ 未开始"
        return f"🔄 进行中 ({completed_count}/{total})"

    @admin.action(description="⚡ 构建全集向量索引 (Build Asset Index)")
    def build_asset_index_action(self, request, queryset):
        success_count = 0
        for asset in queryset:
            try:
                # 1. 获取该 Asset 下的所有 Media (按 sequence_number 排序)
                medias = asset.medias.all().order_by("sequence_number")
                if not medias.exists():
                    continue

                # 2. 聚合数据容器
                aggregated_map = {
                    "dialogue": [],
                    "scene": [],
                    "slice": [],
                    "frame": [],
                }

                for media in medias:
                    # [Fix] 改为从 AnnotationJob 获取数据 (业务标注数据源)
                    # 既然 AnnotationJob 与 Media 是 1:1 (或多对一)，取最新的有效任务
                    job = AnnotationJob.objects.filter(media=media).last()
                    if not job:
                        continue

                    seq = media.sequence_number

                    # 提取并注入 sequence
                    for key in aggregated_map.keys():
                        items = getattr(job, key + "s", [])  # dialogues, scenes, slices, frames
                        if items:
                            # 注入 sequence (浅拷贝避免修改原始数据)
                            for item in items:
                                item_copy = item.copy()
                                item_copy["sequence"] = seq
                                aggregated_map[key].append(item_copy)

                # 3. 构建索引 (Target ID = Asset ID)
                # 这样生成的索引文件会存储在 media/vector_indices/{asset_id}/ 下
                VectorIndexerService.build_and_register(str(asset.id), aggregated_map)
                success_count += 1

            except Exception as e:
                self.message_user(request, f"Asset {asset.title} 构建失败: {e}", level="ERROR")

        if success_count > 0:
            self.message_user(request, f"已成功触发 {success_count} 个资产的索引构建。")
