# 文件路径: apps/workflow/urls.py

from django.urls import include, path

app_name = "workflow"

urlpatterns = [
    path("annotation/", include("apps.workflow.annotation.urls")),
    path("creative/", include("apps.workflow.creative.urls")),
]
