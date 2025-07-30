# 文件路径: media_assets/admin.py

from django.contrib import admin
from .models import Media, Asset
from django.utils.html import format_html
from django.conf import settings
from django.urls import path, reverse, NoReverseMatch
from . import views
from .tasks import generate_narrative_blueprint

print("--- [DEBUG] admin.py file is being loaded ---")

class AssetInline(admin.TabularInline):
    """
    这个类允许我们在 Media 的编辑页面中，以内联表格的形式直接看到和编辑
    其关联的所有 Asset 条目。
    """
    model = Asset
    extra = 1  # 在页面底部提供一个空的行，用于快速添加新的 Asset

    # 在内联表格中只显示最核心的字段，保持界面简洁
    fields = ('sequence_number', 'title', 'l1_status', 'l2_l3_status', 'language', 'copyright_status')
    readonly_fields = ('l1_status', 'l2_l3_status')

    # 提供一个链接，可以从这里直接跳转到每个 Asset 的完整编辑页面
    show_change_link = True

    # 默认按序号排序
    ordering = ('sequence_number',)


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    """
    顶层媒资 (Media) 模型的后台管理配置
    """
    list_display = ('title', 'media_type', 'ingestion_status', 'updated_at', 'workflow_actions')
    search_fields = ('title',)
    list_filter = ('media_type', 'ingestion_status')
    inlines = [AssetInline] # 将上面的 AssetInline 应用到这个 Admin 类中

    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'media_type','ingestion_status')
        }),
        ('外部系统关联与最终产出', {
            'classes': ('collapse',),  # 该分区默认折叠
            'fields': ('label_studio_project_id', 'label_studio_export_file')
        }),
    )

    readonly_fields = ('ingestion_status', 'label_studio_project_id', 'label_studio_export_file')

    actions = ['run_script_modeler']

    @admin.action(description='生成/重新生成叙事蓝图 (后台任务)')
    def run_script_modeler(self, request, queryset):
        for media in queryset:
            generate_narrative_blueprint.delay(str(media.id))
        self.message_user(request, f"已为 {queryset.count()} 个媒资触发了“生成叙事蓝图”的后台任务。")

    # 在列表页显示我们的自定义按钮
    # 我们将所有动作按钮聚合到一个方法中
    def workflow_actions(self, obj):
        actions_html = []

        # 1. 批量加载按钮
        if obj.ingestion_status == 'pending':
            batch_upload_url = reverse('admin:media_assets_media_batch_upload', args=[obj.pk])
            actions_html.append(
                f'<a class="button" href="{batch_upload_url}">批量加载文件</a>'
            )

        # 2. LS 项目创建按钮 (只有在加载完成后才显示)
        if obj.ingestion_status == 'completed':
            ls_url = obj.get_label_studio_project_url()
            if ls_url:
                actions_html.append(
                    f'<a class="button" href="{ls_url}" target="_blank">打开 LS 项目</a>'
                )
            else:
                url = reverse('admin:media_assets_media_create_ls_project', args=[obj.pk])
                actions_html.append(
                    f'<a class="button" href="{url}" target="_blank" style="background-color: #4CAF50;">创建并导入到 LS</a>'
                )

        return format_html(' '.join(actions_html))

    workflow_actions.short_description = '工作流操作'

    def get_urls(self):
        urls = super().get_urls()

        # 获取模型信息的标准方法
        info = self.model._meta.app_label, self.model._meta.model_name

        custom_urls = [
            # LS 项目创建的 URL (已有)
            path('<path:media_id>/create-ls-project/',
                 self.admin_site.admin_view(views.create_label_studio_project),
                 name='%s_%s_create_ls_project' % info),

            # (新增) 批量上传页面的 URL
            path('<path:media_id>/batch-upload/', self.admin_site.admin_view(views.batch_upload_page_view),
                 name='%s_%s_batch_upload' % info),

            # (新增) 文件上传接收器的 API URL
            path('<path:media_id>/api/upload/', self.admin_site.admin_view(views.batch_file_upload_view),
                 name='%s_%s_batch_upload_api' % info),

            # (新增) 任务触发器的 URL
            path('<path:media_id>/trigger-ingest/', self.admin_site.admin_view(views.trigger_ingest_task),
                 name='%s_%s_trigger_ingest' % info),
        ]
        return custom_urls + urls


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    """
    资产条目 (Asset) 模型的后台管理配置
    """
    list_display = (
        '__str__', 'processing_status', 'l1_status', 'l2_l3_status', 'copyright_status', 'updated_at', 'subeditor_actions','annotator_actions'
    )
    list_filter = ('media', 'processing_status', 'l1_status', 'l2_l3_status', 'copyright_status', 'language')
    search_fields = ('title', 'media__title')

    fieldsets = (
        ('基本信息', {
            'fields': ('media', 'title', 'sequence_number', 'language', 'copyright_status')
        }),
        ('输入文件', {
            'fields': ('source_video', 'source_subtitle')
        }),
        ('工作流状态与产出', {
            'classes': ('collapse',),
            'fields': (
                ('processing_status', 'processing_status_changed_at'),
                'processed_video_url',
                ('l1_status', 'l1_status_changed_at'),
                'l1_output_file',
                ('l2_l3_status', 'l2_l3_status_changed_at')
            )
        }),
        ('外部系统关联', {
            'classes': ('collapse',),
            'fields': ('label_studio_task_id',)
        }),
    )

    readonly_fields = (
        'processing_status_changed_at',
        'l1_status_changed_at',
        'l2_l3_status_changed_at',
        'subeditor_actions_in_form',
    )

    def get_fieldsets(self, request, obj=None):
        """动态地将按钮添加到 fieldsets 中"""
        fieldsets = super().get_fieldsets(request, obj)
        if obj:
            # 获取“基本信息”这个分区里的字段列表
            # 注意：fieldsets 是一个元组，我们需要先把它转为列表才能修改
            basic_info_fields = list(fieldsets[0][1]['fields'])

            # 检查按钮是否已经存在，只有在不存在时才添加
            if 'subeditor_actions_in_form' not in basic_info_fields:
                basic_info_fields.append('subeditor_actions_in_form')

            # 将修改后的字段列表写回到 fieldsets 中
            fieldsets[0][1]['fields'] = tuple(basic_info_fields)

        return fieldsets

    def subeditor_actions(self, obj):
        """用于列表页的按钮生成方法"""
        target_url = obj.get_subeditor_url()
        if target_url:
            button_text = "▶️ 打开字幕编辑器"
            button_color = "#FF9800"  # 橙色
            if obj.l1_status == 'completed':
                button_text = "▶️ 重新编辑字幕"
                button_color = "#4CAF50"  # 绿色

            return format_html(
                '<a class="button" href="{}" target="_blank" style="background-color: {};">{}</a>',
                target_url,
                button_color,
                button_text
            )
        return "缺少视频或SRT文件"

    subeditor_actions.short_description = '第一层标注'

    def subeditor_actions_in_form(self, obj):
        """用于编辑页的按钮生成方法"""
        return self.subeditor_actions(obj)

    subeditor_actions_in_form.short_description = '第一层标注操作'

    def annotator_actions(self, obj):
        """在列表页显示 L2/L3 标注的操作按钮"""
        ls_task_url = obj.get_label_studio_task_url()
        if ls_task_url:
            button_text = "▶️ 打开标注任务"
            button_color = "#2196F3"  # 蓝色
            if obj.l2_l3_status == 'completed':
                button_text = "▶️ 查看已完成任务"
                button_color = "#4CAF50"  # 绿色

            return format_html(
                '<a class="button" href="{}" target="_blank" style="background-color: {};">{}</a>',
                ls_task_url,
                button_color,
                button_text
            )
        # 如果这个 Asset 还没有被导入到 LS，则显示创建项目的按钮
        # 这里的逻辑是引导用户先去 Media 级别创建整个项目
        elif not obj.media.label_studio_project_id:
            media_admin_url = reverse('admin:media_assets_media_change', args=[obj.media.id])
            return format_html(
                '先在 <a href="{}">所属媒资</a> 页面创建 LS 项目',
                media_admin_url
            )
        return "尚未导入为LS任务"

    annotator_actions.short_description = '第二/三层标注'