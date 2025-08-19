"""
URL configuration for visify_ssw project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('integrations/ls/', include('apps.media_assets.urls', namespace='media_assets')),
]

# --- [关键修复] 为开发环境提供静态和媒体文件服务 ---
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)