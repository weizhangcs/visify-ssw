"""
URL configuration for visify_ssw project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import RedirectView
from apps.media_assets import views as media_views

urlpatterns = [
    # 强制将 Admin 的默认登录页重定向到 OIDC 认证流程
    # 'oidc_authentication_init' 是 mozilla-django-oidc 库中 /oidc/authenticate/ URL 的名称
    path('admin/login/', RedirectView.as_view(pattern_name='oidc_authentication_init')),
    path('admin/', admin.site.urls),
    path('status/', media_views.status_view, name='status_view'),
    path('integrations/ls/', include('apps.media_assets.urls', namespace='media_assets')),
    path('oidc/', include('mozilla_django_oidc.urls')),
]
