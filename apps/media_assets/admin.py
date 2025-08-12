# 文件路径: apps/media_assets/admin.py

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils.html import format_html
from django.urls import path, reverse
from unfold.admin import ModelAdmin
from unfold.decorators import display, action

from .models import Media, Asset
from . import views
from .tasks import generate_narrative_blueprint
from .forms import MediaAdminForm # <-- 新增导入

print("--- [DEBUG] admin.py file is being loaded ---")

class AssetInline(admin.TabularInline):
    model = Asset
    extra = 0 # <-- 核心修正

    fields = ('sequence_number', 'title', 'l1_status', 'l2_l3_status', 'language', 'copyright_status')
    readonly_fields = ('l1_status', 'l2_l3_status')
    show_change_link = True
    ordering = ('sequence_number',)


@admin.register(Media)
class MediaAdmin(ModelAdmin):
    form = MediaAdminForm # <-- 核心修正：使用自定义表单

    list_display = (
        'title',
        'media_type',
        'ingestion_status',
        'updated_at',
        'batch_upload_action',
        'label_studio_action',
        'generate_blueprint_button'
    )
    search_fields = ('title',)
    list_filter = ('media_type', 'ingestion_status')
    inlines = [AssetInline]

    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'media_type','ingestion_status')
        }),
        ('外部系统关联与最终产出', {
            'classes': ('collapse',),
            'fields': ('label_studio_project_id', 'label_studio_export_file')
        }),
    )

    readonly_fields = ('ingestion_status', 'label_studio_project_id', 'label_studio_export_file')

    actions = []

    @display(
        header=True,
        description="批量加载文件",
        label="批量加载"
    )
    def batch_upload_action(self, obj):
        if obj.ingestion_status == 'pending':
            batch_upload_url = reverse('admin:media_assets_media_batch_upload', args=[obj.pk])
            return format_html(
                '<a href="{}" class="button">批量加载文件</a>',
                batch_upload_url
            )
        return "✓ 已加载"

    @display(
        header=True,
        description="与 Label Studio 同步",
        label="标注平台"
    )
    def label_studio_action(self, obj):
        if obj.ingestion_status == 'completed':
            ls_url = obj.get_label_studio_project_url()
            if ls_url:
                return format_html(
                    '<a href="{}" class="button" target="_blank">打开 LS 项目</a>',
                    ls_url
                )
            else:
                url = reverse('admin:media_assets_media_create_ls_project', args=[obj.pk])
                return format_html(
                    '<a href="{}" class="button" style="background-color: var(--button-bg);">创建并导入到 LS</a>',
                    url
                )
        return "—"

    @display(
        header=True,
        description="生成叙事蓝图",
        label="生成蓝图"
    )
    def generate_blueprint_button(self, obj):
        action_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_generate_blueprint", args=[obj.pk])
        if obj.label_studio_export_file:
             return format_html(
                '<a href="{}" class="button">{}</a>',
                action_url,
                "生成/更新蓝图"
            )
        return "无标注数据"

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            path('<path:media_id>/create-ls-project/', self.admin_site.admin_view(views.create_label_studio_project), name='%s_%s_create_ls_project' % info),
            path('<path:media_id>/batch-upload/', self.admin_site.admin_view(views.batch_upload_page_view), name='%s_%s_batch_upload' % info),
            path('<path:media_id>/api/upload/', self.admin_site.admin_view(views.batch_file_upload_view), name='%s_%s_batch_upload_api' % info),
            path('<path:media_id>/trigger-ingest/', self.admin_site.admin_view(views.trigger_ingest_task), name='%s_%s_trigger_ingest' % info),
            path('<path:media_id>/generate-blueprint/', self.admin_site.admin_view(views.generate_blueprint), name='%s_%s_generate_blueprint' % info),
        ]
        return custom_urls + urls


@admin.register(Asset)
class AssetAdmin(ModelAdmin):
    list_display = (
        '__str__',
        'processing_status',
        'l1_status',
        'l2_l3_status',
        'subeditor_actions',
        'annotator_actions',
        'updated_at',
    )
    list_filter = ('media', 'processing_status', 'l1_status', 'l2_l3_status', 'copyright_status', 'language')
    search_fields = ('title', 'media__title')

    fieldsets = (
        ('基本信息', {'fields': ('media', 'title', 'sequence_number', 'language', 'copyright_status')}),
        ('输入文件', {'fields': ('source_video', 'source_subtitle')}),
        ('工作流状态与产出', {'classes': ('collapse',), 'fields': (('processing_status', 'processing_status_changed_at'), 'processed_video_url', ('l1_status', 'l1_status_changed_at'), 'l1_output_file', ('l2_l3_status', 'l2_l3_status_changed_at'))}),
        ('外部系统关联', {'classes': ('collapse',), 'fields': ('label_studio_task_id',)}),
    )

    readonly_fields = (
        'processing_status_changed_at',
        'l1_status_changed_at',
        'l2_l3_status_changed_at',
    )

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            path('<uuid:asset_id>/start-l1/', self.admin_site.admin_view(views.start_l1_annotation), name='%s_%s_start_l1_annotation' % info),
            path('<uuid:asset_id>/start-l2l3/', self.admin_site.admin_view(views.start_l2_l3_annotation), name='%s_%s_start_l2l3_annotation' % info),
        ]
        return custom_urls + urls

    @display(header=True, description="第一层标注", label="字幕编辑器")
    def subeditor_actions(self, obj):
        button_text = "▶️ 打开编辑器"
        if obj.l1_status == 'completed':
            button_text = "✓ 重新编辑"
        target_url = reverse('admin:media_assets_asset_start_l1_annotation', args=[obj.pk])
        return format_html('<a class="button" href="{}" target="_blank">{}</a>', target_url, button_text)

    @display(header=True, description="第二/三层标注", label="语义标注")
    def annotator_actions(self, obj):
        if obj.media.label_studio_project_id and obj.label_studio_task_id:
            button_text = "▶️ 打开任务"
            if obj.l2_l3_status == 'completed':
                button_text = "✓ 查看任务"
            target_url = reverse('admin:media_assets_asset_start_l2l3_annotation', args=[obj.pk])
            return format_html('<a class="button" href="{}" target="_blank">{}</a>', target_url, button_text)
        elif not obj.media.label_studio_project_id:
            media_admin_url = reverse('admin:media_assets_media_change', args=[obj.media.id])
            return format_html('先在 <a href="{}">所属媒资</a> 创建项目', media_admin_url)
        return "尚未导入"