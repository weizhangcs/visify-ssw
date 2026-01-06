# -----------------------------------------------------------------------------
# [WORKFLOW ADMIN REGISTRY]
# -----------------------------------------------------------------------------
# This file acts as a central registry for all admin interfaces related to
# the workflow app. It ensures that Django's admin autodiscover mechanism
# finds and registers all separated admin classes.
#
# To add a new admin module, simply import it here.
# -----------------------------------------------------------------------------

# 文件路径: apps/workflow/admin.py

from .annotation.admin import AnnotationProjectAdmin
from .creative.admin import CreativeProjectAdmin
from .delivery.admin import DeliveryJobAdmin
from .inference.admin import InferenceProjectAdmin

# 显式声明导出列表，既满足了 Flake8 的 F401 检查，
# 也明确了该模块作为 "Admin Registry" 的职责。
__all__ = [
    "AnnotationProjectAdmin",
    "CreativeProjectAdmin",
    "DeliveryJobAdmin",
    "InferenceProjectAdmin",
    "AnnotationProjectAdmin",
]
