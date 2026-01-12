# 文件路径: apps/media_assets/admin.py

from django.contrib import admin
from django.db import models
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.decorators import display
from unfold.widgets import UnfoldAdminTextareaWidget

from . import views
from .models import Asset, Media


@admin.register(Asset)
class AssetAdmin(ModelAdmin):
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
        models.JSONField: {"widget": UnfoldAdminTextareaWidget(attrs={"rows": 3})},
    }

    list_display = (
        "title",
        "asset_type",
        "orientation",
        "language",
        "copyright_status",
        "upload_status",
        "created",
        "modified",
        "batch_upload_action",
    )
    list_filter = ("asset_type", "orientation", "language", "copyright_status", "upload_status")
    search_fields = ("title",)
    inlines = []
    actions = []
    # [核心修复] 增加分页
    list_per_page = 20

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "description",
                    ("asset_type", "content_genre"),
                    ("language", "orientation"),
                    "known_characters",
                    ("copyright_status", "upload_status"),
                ),
            },
        ),
    )

    @display(header=True, description="文件上传状态与操作", label="文件上传")
    def batch_upload_action(self, obj):
        # --- 核心修复：使用正确的 URL 名称 ---
        url_name = f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_batch_upload"  # noqa: E231
        batch_upload_url = reverse(url_name, args=[obj.pk])

        if obj.upload_status == "pending":
            return format_html('<a href="{}" class="button">上传文件</a>', batch_upload_url)
        elif obj.upload_status == "uploading":
            return "上传中..."
        elif obj.upload_status == "failed":
            return "上传失败"
        return "✓ 上传完成"

    def get_urls(self):
        """

        :return:
        """
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            path(
                "<path:asset_id>/batch-upload/",
                self.admin_site.admin_view(views.batch_upload_page_view),
                name="%s_%s_batch_upload" % info,
            ),
            path(
                "<path:asset_id>/api/upload/",
                self.admin_site.admin_view(views.batch_file_upload_view),
                name="%s_%s_batch_upload_api" % info,
            ),
            path(
                "<path:asset_id>/trigger-ingest/",
                self.admin_site.admin_view(views.trigger_ingest_task),
                name="%s_%s_trigger_ingest" % info,
            ),
        ]
        return custom_urls + urls


@admin.register(Media)
class MediaAdmin(ModelAdmin):
    """
    (V5.0 修复版)
    同步适配 Media 模型重构，移除已废弃的 URL 字段引用。
    """

    list_display = (
        "__str__",
        "asset",
        "sequence_number",
        "modified",
    )

    # [核心修复] 增强筛选与搜索
    list_filter = ("asset__title", "asset__asset_type")  # 支持按资产名和类型筛选
    search_fields = ("title", "asset__title")  # 支持搜文件名或资产名

    # [核心修复] 增加分页
    list_per_page = 20

    # [修复] 移除 processed_video_url 引用
    fieldsets = (
        ("基本信息", {"fields": ("asset", "title", "sequence_number")}),
        ("源文件", {"classes": ("collapse",), "fields": ("source_video", "source_subtitle")}),
    )

    # [修复] 移除不存在的 readonly_fields
    # source_video 和 source_subtitle 是 FileField，Admin 默认会以链接形式显示
    # 如果您希望它们只读，可以放进来，但不要放已删除的 xxx_url 字段
    readonly_fields = ()

    # 移除所有自定义的 get_urls 和 action 方法
