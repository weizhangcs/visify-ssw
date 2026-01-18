# 文件路径: apps/workflow/urls.py

from django.urls import include, path

app_name = "workflow"

urlpatterns = [
    # 将所有以 'annotation/' 开头的请求，都转发给 annotation 子包的 urls.py 去处理
    path("annotation/", include("apps.workflow.annotation.urls")),
    path("creative/", include("apps.workflow.creative.urls")),
    # 为 transcoding 和 delivery 预留位置，即使它们现在没有自己的 URL
    # path('transcoding/', include('apps.workflow.transcoding.urls')),
    # path('delivery/', include('apps.workflow.delivery.urls')),
]
