# 文件路径: apps/atomflow/apps.py

from django.apps import AppConfig


class AtomflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    # 定义 App 的逻辑名称
    name = "apps.atomflow"
    # 在 Django Admin 中显示的分类名称
    verbose_name = "Atomflow 算子化框架"

    def ready(self):
        """
        此处可以放置信号注册或初始化逻辑。
        当前旁路测试阶段，保持简洁。
        """
        pass
