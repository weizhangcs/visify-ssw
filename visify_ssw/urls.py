"""
URL configuration for visify_ssw project.
"""
from django.contrib import admin
from django.urls import path, include
from apps.media_assets import views as media_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('integrations/ls/', include('apps.media_assets.urls', namespace='media_assets')),
]