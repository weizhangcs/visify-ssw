from django import forms
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from apps.media_assets.models import Media

from .models import Material, RefineryAtomPipeline, RefineryAtomRule
from .scheduler import RefineryAtomScheduler

# --- Forms ---


class RefineryAtomPipelineForm(forms.ModelForm):
    """
    [业务表单] 简化流水线创建
    用户只需选择 Media，系统自动处理 Material 的关联逻辑。
    """

    media_select = forms.ModelChoiceField(
        queryset=Media.objects.all(), label="选择媒体资产", help_text="选择一个媒体文件，系统将自动为其创建或关联精炼物料(Material)。", required=False
    )

    class Meta:
        model = RefineryAtomPipeline
        fields = ["name", "rule", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. 如果是编辑模式，回填当前的 Media
        if self.instance.pk and self.instance.material:
            self.fields["media_select"].initial = self.instance.material.media
            # 锁定媒体选择，防止破坏关联
            self.fields["media_select"].disabled = True
            self.fields["media_select"].help_text = "流水线创建后不可更改关联媒体。"

        # 2. 如果是创建模式，尝试设置默认规则
        if not self.instance.pk:
            # 默认选中第一个规则 (假设为全流水线配置)
            first_rule = RefineryAtomRule.objects.first()
            if first_rule:
                self.fields["rule"].initial = first_rule

            # 创建时隐藏状态，默认为 PENDING
            if "status" in self.fields:
                self.fields["status"].widget = forms.HiddenInput()


# --- Admins ---


@admin.register(RefineryAtomPipeline)
class RefineryAtomPipelineAdmin(ModelAdmin):
    form = RefineryAtomPipelineForm
    list_display = ("name", "status_badge", "rule", "linked_media", "run_action", "created")
    list_filter = ("status", "rule")
    search_fields = ("name", "target_id", "error_log")
    readonly_fields = ("target_id", "material", "metrics", "error_log", "stop_point", "created", "modified")

    # 优化 JSON 字段显示
    formfield_overrides = {}

    # 仅在创建时显示 media_select，详情页显示只读的 material/target_id
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("name", "media_select", "rule", "status"),
            },
        ),
    )

    fieldsets = (
        (
            "基本信息",
            {
                "fields": ("name", "status", "rule"),
            },
        ),
        (
            "关联信息",
            {
                "fields": ("media_select", "material", "target_id"),
            },
        ),
        (
            "执行状态",
            {
                "fields": ("metrics", "error_log", "stop_point", "created", "modified"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        """
        重写保存逻辑：
        1. 获取选中的 Media
        2. Get/Create Material
        3. 关联 Pipeline
        """
        if not change:  # 创建模式
            media = form.cleaned_data.get("media_select")
            if media:
                # 核心业务逻辑：确保 Material 存在
                material, created = Material.objects.get_or_create(media=media)

                obj.material = material
                obj.target_id = str(material.id)

                # 自动生成名称 (如果用户没填)
                if not obj.name:
                    obj.name = f"Refinery-{media.title}"

        super().save_model(request, obj, form, change)

    # --- 自定义动作与视图 ---

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<path:object_id>/start/",
                self.admin_site.admin_view(self.start_pipeline_view),
                name="atomflow_refineryatompipeline_start",
            ),
        ]
        return custom_urls + urls

    def start_pipeline_view(self, request, object_id):
        pipeline = get_object_or_404(RefineryAtomPipeline, pk=object_id)

        if pipeline.status in [RefineryAtomPipeline.Status.RUNNING, RefineryAtomPipeline.Status.SUCCESS]:
            messages.warning(request, f"流水线 {pipeline.name} 已经在运行或已完成。")
        else:
            try:
                # [Real Logic] 调用调度器启动
                RefineryAtomScheduler.start_pipeline(str(pipeline.id))
                messages.success(request, f"🚀 流水线 {pipeline.name} 已点火启动！")
            except Exception as e:
                messages.error(request, f"启动失败: {str(e)}")

        return redirect("admin:atomflow_refineryatompipeline_changelist")

    # --- 列表页展示 ---

    @admin.display(description="状态")
    def status_badge(self, obj):
        colors = {
            "PENDING": "gray",
            "RUNNING": "blue",
            "SUCCESS": "green",
            "FAILED": "red",
            "STOPPED": "orange",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            f'<span class="px-2 py-1 rounded text-xs font-bold bg-{color}-100 text-{color}-800">{obj.get_status_display()}</span>'  # noqa: E501
        )

    @admin.display(description="关联媒体")
    def linked_media(self, obj):
        if obj.material and obj.material.media:
            return obj.material.media.title
        return "-"

    @admin.display(description="操作")
    def run_action(self, obj):
        if obj.status in ["PENDING", "FAILED", "STOPPED"]:
            # 注意：这里的 name 依赖于 model 的 app_label，如果 refinery 是独立 app，可能需要调整
            # 但通常 Django 会自动处理为 admin:applabel_modelname_start
            # 如果 atomflow 是主 app，这里通常是 admin:atomflow_refineryatompipeline_start
            url = reverse("admin:atomflow_refineryatompipeline_start", args=[obj.pk])
            return format_html(
                '<a href="{}" class="text-white bg-indigo-600 hover:bg-indigo-700 font-medium rounded-lg text-sm px-3 py-1.5 focus:outline-none">🚀 启动</a>',  # noqa: E501
                url,
            )
        return "-"
