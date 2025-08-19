from django.urls import path
from . import views

app_name = 'media_assets'
urlpatterns = [
    path('asset/<uuid:asset_id>/save-l1-output/', views.save_l1_output, name='save_l1_output'),
]