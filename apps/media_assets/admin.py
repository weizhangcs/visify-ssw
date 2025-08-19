# 文件路径: apps/media_assets/admin.py

from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from django.urls import path, reverse
from unfold.admin import ModelAdmin
from unfold.decorators import display, action
from unfold.contrib.forms.widgets import WysiwygWidget
from .models import Media, Asset
from . import views
from django.utils.safestring import mark_safe

class AssetInline(admin.TabularInline):
    model = Asset
    extra = 0 # <-- 核心修正

    fields = ('sequence_number', 'title', 'l1_status', 'l2_l3_status')
    readonly_fields = ('l1_status', 'l2_l3_status')
    show_change_link = True
    ordering = ('sequence_number',)

@admin.register(Media)
class MediaAdmin(ModelAdmin):
    #form = MediaAdminForm
    formfield_overrides = {
        models.TextField: {"widget": WysiwygWidget},
    }

    list_display = (
        'title',
        'media_type',
        'language',
        'copyright_status',
        'updated_at',
        'batch_upload_action',
        'character_audit_action',
        'processing_status',
        'label_studio_action',
        'generate_blueprint_button',
        'validate_blueprint_action',
    )
    search_fields = ('title',)
    list_filter = ('media_type', 'upload_status', 'processing_status','language','copyright_status',)
    inlines = [AssetInline]

    fieldsets = (
        (None, {
            "fields": [
                (
                    "title",
                    'language',
                    'copyright_status',
                ),
                (
                    "media_type",
                    "upload_status",
                    "processing_status",
                ),
                (
                    "description",
                )
            ]
        }),
        ('外部系统关联与最终产出', {
            'classes': ('collapse',),
            'fields': ('label_studio_project_id', 'label_studio_export_file', 'final_blueprint_file','character_audit_report','display_blueprint_validation_report')
        }),
    )

    readonly_fields = ('upload_status', 'processing_status', 'label_studio_project_id', 'final_blueprint_file','character_audit_report','display_blueprint_validation_report')

    actions = []

    @display(
        header=True,
        description="文件上传状态与操作",
        label="文件上传"
    )
    def batch_upload_action(self, obj):
        if obj.upload_status == 'pending':
            batch_upload_url = reverse('admin:media_assets_media_batch_upload', args=[obj.pk])
            return format_html(
                '<a href="{}" class="button">上传文件</a>',
                batch_upload_url
            )
        elif obj.upload_status == 'uploading':
            return "上传中..."
        elif obj.upload_status == 'failed':
            return "上传失败"
        return "✓ 上传完成"

    @display(
        header=True,
        description="与 Label Studio 同步",
        label="标注平台"
    )
    def label_studio_action(self, obj):
        if obj.processing_status == 'completed':
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
        description="第一层(ASS)产出物审计",
        label="L1审计-角色"
    )
    def character_audit_action(self, obj):
        action_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_generate_character_report", args=[obj.pk])
        return format_html(
            '<a href="{}" class="button">生成角色清单</a>',
            action_url
        )

    @display(
        header=True,
        description="第二/三层(JSON)产出物审计",
        label="L2/L3审计-验证"
    )
    def validate_blueprint_action(self, obj):
        if obj.final_blueprint_file:
            action_url = reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_validate_blueprint",
                                 args=[obj.pk])
            return format_html(
                '<a href="{}" class="button">验证叙事蓝图</a>',
                action_url
            )
        return "无蓝图文件"

    @display(description="叙事蓝图验证报告")
    def display_blueprint_validation_report(self, obj):
        """将JSON格式的验证报告渲染为HTML列表。"""
        if not obj.blueprint_validation_report:
            return "尚未生成报告。"

        errors = obj.blueprint_validation_report.get("errors", [])
        if not errors:
            return mark_safe("✅ 验证通过，未发现任何错误。")

        html = "<ul>"
        for error in errors:
            html += (
                f"<li><strong>[{error['rule_violated']}]</strong> "
                f"Scene ID: {error.get('scene_id', 'N/A')}<br>"
                f"<small style='color: #666;'>Details: {error['error_details']}</small></li>"
            )
        html += "</ul>"
        return mark_safe(html)

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
            path('<path:media_id>/mark-l2l3-complete/', self.admin_site.admin_view(views.mark_media_l2l3_as_complete),name='%s_%s_mark_l2l3_complete' % info),
            path('<path:media_id>/generate-character-report/',self.admin_site.admin_view(views.generate_character_report_view),name='%s_%s_generate_character_report' % info),
            path('<path:media_id>/validate-blueprint/', self.admin_site.admin_view(views.validate_blueprint_view), name='%s_%s_validate_blueprint' % info),
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
    list_filter = ('media', 'processing_status', 'l1_status', 'l2_l3_status')
    search_fields = ('title', 'media__title')

    fieldsets = (
        ('基本信息', {'fields': ('media', 'title', 'sequence_number')}),
        ('输入文件与手动处理', {
            'classes': ('collapse',),
            'fields': ('source_video', 'source_subtitle', 'manual_processing_trigger')
        }),
        ('工作流状态与产出', {'classes': ('collapse',), 'fields': (('processing_status', 'processing_status_changed_at'), 'processed_video_url', ('l1_status', 'l1_status_changed_at'), 'l1_output_file', ('l2_l3_status', 'l2_l3_status_changed_at'))}),
        ('外部系统关联', {'classes': ('collapse',), 'fields': ('label_studio_task_id',)}),
    )

    readonly_fields = (
        'processing_status_changed_at',
        'l1_status_changed_at',
        'l2_l3_status_changed_at',
        'manual_processing_trigger',
    )

    def get_urls(self):
        urls = super().get_urls()
        info = self.model._meta.app_label, self.model._meta.model_name
        custom_urls = [
            path('<uuid:asset_id>/start-l1/', self.admin_site.admin_view(views.start_l1_annotation), name='%s_%s_start_l1_annotation' % info),
            path('<uuid:asset_id>/start-l2l3/', self.admin_site.admin_view(views.start_l2_l3_annotation), name='%s_%s_start_l2l3_annotation' % info),
            path('<uuid:asset_id>/trigger-single-processing/', self.admin_site.admin_view(views.trigger_single_asset_processing), name='%s_%s_trigger_single_processing' % info),
        ]
        return custom_urls + urls

    @display(description="触发处理")
    def manual_processing_trigger(self, obj):
        if obj.source_video:
            action_url = reverse('admin:media_assets_asset_trigger_single_processing', args=[obj.pk])
            return format_html(
                '<a href="{}" class="button">⚙️ 手动处理文件</a>',
                action_url
            )
        return "请先上传源视频文件。"

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