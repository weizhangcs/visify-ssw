# 文件路径: apps/workflow/annotation/forms.py

from django import forms
from unfold.widgets import UnfoldAdminTextareaWidget

from .projects import AnnotationProject


class AnnotationProjectForm(forms.ModelForm):
    """
    (V5.0) 标注项目基础表单
    仅用于创建时的基础信息录入：资产、编码配置、名称。
    后续的复杂字段（如产出物路径）由系统自动生成。
    """

    class Meta:
        model = AnnotationProject
        # 虽然这里写了 __all__，但实际显示的字段由 Admin 类的 fieldsets 控制
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 优化描述字段的输入体验，保持与系统其他部分风格一致
        if "description" in self.fields:
            self.fields["description"].widget = UnfoldAdminTextareaWidget(attrs={"rows": 3})

        # 确保创建时必须选择 Asset (虽然 Model 层有约束，这里可以在前端加强体验)
        if "asset" in self.fields:
            self.fields["asset"].required = True
            # 你可以在这里过滤 Asset，比如只显示未关联项目的 Asset，视业务需求而定
            # self.fields["asset"].queryset = ...
