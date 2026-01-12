from django import forms
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.widgets import UnfoldAdminSelectWidget

from apps.atomflow.refinery.models import Material, RefineryAtomPipeline, RefineryAtomRule
from apps.atomflow.refinery.scheduler import RefineryAtomScheduler
from apps.media_assets.models import Asset, Media

# --- Forms ---


class RefineryAtomPipelineForm(forms.ModelForm):
    """
    [业务表单] 简化流水线创建
    用户只需选择 Asset，系统自动处理该 Asset 下所有 Media 的 Pipeline 创建。
    """

    asset_select = forms.ModelChoiceField(
        queryset=Asset.objects.all(),
        label="选择内容资产",
        help_text="选择一个内容资产(Asset)，系统将自动为其下属的所有媒体文件(Media)创建流水线。",
        required=False,
        # [Optimization] 使用 Unfold 原生美化控件 (带前端搜索，非 AJAX)
        widget=UnfoldAdminSelectWidget,
    )

    class Meta:
        model = RefineryAtomPipeline
        fields = ["name", "rule", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. 如果是编辑模式，回填当前的 Asset
        if self.instance.pk and self.instance.material and self.instance.material.media:
            asset = self.instance.material.media.asset
            if asset:
                self.fields["asset_select"].initial = asset
            # 锁定选择
            self.fields["asset_select"].disabled = True
            self.fields["asset_select"].help_text = "流水线创建后不可更改关联资产。"

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
    list_display = ("name", "status_badge", "rule", "linked_asset", "linked_media", "run_action", "created")
    list_filter = ("status", "rule")
    search_fields = ("name", "target_id", "error_log")
    readonly_fields = ("target_id", "material", "metrics", "error_log", "stop_point", "created", "modified")
    actions = ["start_selected_pipelines"]

    # 优化 JSON 字段显示
    formfield_overrides = {}

    # 仅在创建时显示 asset_select
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("name", "asset_select", "rule", "status"),
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
                "fields": ("asset_select", "material", "target_id"),
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
        1. 获取选中的 Asset
        2. 遍历 Asset 下的所有 Media
        3. 批量创建 Pipeline
        """
        if not change:  # 创建模式
            asset = form.cleaned_data.get("asset_select")
            if asset:
                medias = list(Media.objects.filter(asset=asset).order_by("sequence_number"))

                if not medias:
                    messages.warning(request, f"资产 [{asset.title}] 下没有媒体文件，无法创建流水线。")
                    return

                # 核心逻辑：批量创建
                target_media_for_obj = None
                other_medias_to_create = []

                for m in medias:
                    mat, _ = Material.objects.get_or_create(media=m)
                    # 检查是否已存在 Pipeline
                    if not hasattr(mat, "pipeline"):
                        if target_media_for_obj is None:
                            target_media_for_obj = m
                        else:
                            other_medias_to_create.append(m)

                if target_media_for_obj is None:
                    messages.warning(request, f"资产 [{asset.title}] 下的所有媒体文件均已存在流水线。")
                    return

                # 配置 obj (第一个可用的 Media)
                mat_obj, _ = Material.objects.get_or_create(media=target_media_for_obj)
                obj.material = mat_obj
                obj.target_id = str(mat_obj.id)
                if not obj.name:
                    obj.name = f"Refinery-{target_media_for_obj.title}"

                # 保存 obj
                super().save_model(request, obj, form, change)

                # 创建其他的
                rule = obj.rule
                status = obj.status
                count = 0
                for m in other_medias_to_create:
                    mat, _ = Material.objects.get_or_create(media=m)
                    RefineryAtomPipeline.objects.create(
                        name=f"Refinery-{m.title}", rule=rule, material=mat, target_id=str(mat.id), status=status
                    )
                    count += 1

                total = 1 + count
                messages.success(request, f"成功为资产 [{asset.title}] 创建了 {total} 条流水线。请在列表中选中它们并使用“批量启动”功能。")
                return

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

    @admin.action(description="🚀 批量启动选中流水线")
    def start_selected_pipelines(self, request, queryset):
        """
        [Admin Action] 批量启动流水线。
        解决多集短剧场景下需要逐个点击启动的交互痛点。
        """
        # 过滤掉已经在运行或已成功的，避免重复触发
        candidates = queryset.exclude(
            status__in=[RefineryAtomPipeline.Status.RUNNING, RefineryAtomPipeline.Status.SUCCESS]
        )

        if not candidates.exists():
            self.message_user(request, "未选中可启动的流水线 (可能已在运行或已完成)。", messages.WARNING)
            return

        success_count = 0
        fail_count = 0

        for pipeline in candidates:
            try:
                RefineryAtomScheduler.start_pipeline(str(pipeline.id))
                success_count += 1
            except Exception:
                fail_count += 1

        if success_count > 0:
            self.message_user(request, f"🚀 已成功触发 {success_count} 条流水线。", messages.SUCCESS)

        if fail_count > 0:
            self.message_user(request, f"❌ {fail_count} 条流水线启动失败，请查看后台日志。", messages.ERROR)

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

    @admin.display(description="关联资产")
    def linked_asset(self, obj):
        if obj.material and obj.material.media and obj.material.media.asset:
            return obj.material.media.asset.title
        return "-"

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
