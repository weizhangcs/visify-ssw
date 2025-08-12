# apps/media_assets/dashboards.py
from django.urls import reverse
from django.conf import settings
from unfold.widgets import (
    Kpi,
    List,
    Shortcut,
)
from .models import Media, Asset

def build_dashboard(request):
    """
    构建 VSS-Workbench 的自定义仪表盘。
    这个函数由 unfold 主题在渲染首页时调用。
    """

    # 1. 关键指标 (KPIs)
    # 统计当前处于各个关键工作流状态的条目数量
    pending_media_count = Media.objects.filter(ingestion_status='pending').count()
    l1_in_progress_count = Asset.objects.filter(l1_status='in_progress').count()
    l2_l3_in_progress_count = Asset.objects.filter(l2_l3_status='in_progress').count()

    # 2. 最近更新的资产列表
    # 显示最近被修改过的5个剧集，方便快速跟进
    latest_assets = Asset.objects.order_by('-updated_at')[:5]

    # 3. 快捷方式
    # 提供指向核心操作和外部工具的快速链接
    add_media_url = reverse('admin:media_assets_media_add')

    # 最终返回一个由列表构成的、描述仪表盘布局的结构
    return [
        [
            # 第一行：三个KPI组件
            Kpi("待加载的媒资", pending_media_count),
            Kpi("L1 标注中", l1_in_progress_count),
            Kpi("L2/L3 标注中", l2_l3_in_progress_count),
        ],
        [
            # 第二行左侧：一个列表组件
            List(
                title="最近更新的剧集",
                queryset=latest_assets,
                list_display=["__str__", "l1_status", "l2_l3_status", "updated_at"]
            ),
            # 第二行右侧：一组快捷方式组件
            [
                Shortcut(title="新增媒资", url=add_media_url, icon="add"),
                Shortcut(
                    title="Label Studio",
                    url=settings.LABEL_STUDIO_PUBLIC_URL,
                    icon="launch",
                    target="_blank" # 在新标签页打开
                ),
            ]
        ]
    ]