from django.urls import path
from . import views

app_name = 'media_assets'
urlpatterns = [
    # 这个 URL 用于接收来自 Label Studio 的“标记完成”回调
    path('asset/<uuid:asset_id>/mark-as-complete/', views.mark_asset_as_complete, name='mark_asset_as_complete'),
    path('asset/<uuid:asset_id>/save-l1-output/', views.save_l1_output, name='save_l1_output'),
]