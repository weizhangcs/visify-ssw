from django.urls import path

from . import views

# namespace: workflow:scene_orchestration
app_name = "scene_orchestration"

urlpatterns = [
    # ==========================================
    # 场景编排 (Orchestration)
    # ==========================================
    # 1. 页面入口
    path("orchestration/<uuid:project_id>/", views.annotation_orchestration_entry, name="orchestration_entry"),
    # 2. 数据加载 API
    path("orchestration/<uuid:project_id>/data/", views.orchestration_get_data_api, name="orchestration_data"),
    # 3. 数据保存 API
    path("orchestration/<uuid:project_id>/save/", views.orchestration_save_api, name="orchestration_save"),
]
