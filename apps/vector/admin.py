# 文件路径: apps/vector/admin.py

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import VectorIndex, VectorSourceJob
from .services.indexer import VectorIndexerService


@admin.register(VectorIndex)
class VectorIndexAdmin(ModelAdmin):
    list_display = ("target_id", "index_type", "vector_count", "dimension", "is_active", "modified")
    list_filter = ("index_type", "is_active", "model_name")
    search_fields = ("target_id",)
    readonly_fields = ("target_id", "index_type", "file_path", "vector_count", "dimension", "model_name")


@admin.register(VectorSourceJob)
class VectorSourceJobAdmin(ModelAdmin):
    """
    [Debug/Ops] 向量数据源管理
    允许管理员直接从 AnnotationJob 构建索引。
    """

    list_display = ("id", "media_title", "project_name", "status", "modified")
    list_filter = ("status", "project")
    search_fields = ("id", "media__title")
    actions = ["build_vector_index_action"]

    @admin.display(description="媒体标题")
    def media_title(self, obj):
        return obj.media.title

    @admin.display(description="所属项目")
    def project_name(self, obj):
        return obj.project.name

    @admin.action(description="⚡ 构建向量索引 (Build Index)")
    def build_vector_index_action(self, request, queryset):
        success_count = 0
        for job in queryset:
            try:
                # 映射数据 (只提取 Processor 支持的字段)
                data_map = {
                    "dialogue": job.dialogues,
                    "scene": job.scenes,
                    "slice": job.slices,
                    "frame": job.frames,
                }
                VectorIndexerService.build_and_register(str(job.id), data_map)
                success_count += 1
            except Exception as e:
                self.message_user(request, f"Job {job.id} 构建失败: {e}", level="ERROR")

        if success_count > 0:
            self.message_user(request, f"已成功触发 {success_count} 个任务的索引构建。")
