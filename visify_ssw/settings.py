"""
Django settings for visify_ssw project.
"""
import os
from pathlib import Path
from decouple import config
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('DJANGO_SECRET_KEY')
DEBUG = config('DJANGO_DEBUG', default=True, cast=bool)
ALLOWED_HOSTS_str = config('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_str.split(',') if host.strip()]

INSTALLED_APPS = [
    'unfold',
    'unfold.contrib.forms',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.media_assets.apps.MediaAssetsConfig',
    'apps.configuration.apps.ConfigurationConfig',
    'apps.jobs.apps.JobsConfig',
    'corsheaders',
    'solo',
    'crispy_forms',
    'crispy_tailwind',
]

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
)

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'visify_ssw.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'visify_ssw.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('POSTGRES_DB'),
        'USER': config('POSTGRES_USER'),
        'PASSWORD': config('POSTGRES_PASSWORD'),
        'HOST': 'db',
        'PORT': '5432',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media_root'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_BROKER_URL", default="redis://redis:6-379/0")
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_IMPORTS = ('apps.media_assets.tasks',)

AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='')
AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default='')
AWS_S3_PROCESSED_VIDEOS_PREFIX = config('AWS_S3_PROCESSED_VIDEOS_PREFIX', default='processed_videos/')
AWS_S3_SOURCE_SUBTITLES_PREFIX = config('AWS_S3_SOURCE_SUBTITLES_PREFIX', default='source_subtitles/')

CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://localhost:3001"]
CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]
CORS_ALLOW_HEADERS = ["accept", "authorization", "content-type", "user-agent", "x-csrftoken", "x-requested-with"]

SUBEDITOR_URL = config("SUBEDITOR_URL", default="http://subeditor:3000")
LABEL_STUDIO_URL = config('LABEL_STUDIO_INTERNAL_URL', default='http://label-studio:8080')
LOCAL_MEDIA_URL_BASE = config('LOCAL_MEDIA_URL_BASE', default='http://localhost:9999')
LABEL_STUDIO_PUBLIC_URL = config("LABEL_STUDIO_PUBLIC_URL", default="http://localhost:8081")
SUBEDITOR_PUBLIC_URL = config("SUBEDITOR_PUBLIC_URL", default="http://localhost:3000")
LABEL_STUDIO_ACCESS_TOKEN = config('LABEL_STUDIO_ACCESS_TOKEN', default='')

STORAGE_BACKEND = config('STORAGE_BACKEND', default='local')
FFMPEG_VIDEO_BITRATE = config('FFMPEG_VIDEO_BITRATE', default='2M')
FFMPEG_VIDEO_PRESET = config('FFMPEG_VIDEO_PRESET', default='fast')

UNFOLD = {
    "SITE_TITLE": "Visify Story Studio",
    "SIDEBAR": {
        "navigation": [
            {'title': '工作台', 'items': [{'title': '仪表盘', 'icon': 'space_dashboard', 'link': reverse_lazy('admin:index')}]},
            {'title': '媒资管理', 'separator': True, 'items': [{'title': '媒资 (作品)', 'link': reverse_lazy('admin:media_assets_media_changelist'), 'icon': 'movie'}, {'title': '资产条目 (剧集)', 'link': reverse_lazy('admin:media_assets_asset_changelist'), 'icon': 'video_library'}]},
            {'title': '工作流任务', 'separator': True, 'items': [{'title': '转码任务', 'link': reverse_lazy('admin:jobs_transcodingjob_changelist'), 'icon': 'movie'}]},
            {'title': '系统设置', 'separator': True, 'items': [{'title': '集成设置', 'link': reverse_lazy('admin:configuration_integrationsettings_changelist'), 'icon': 'hub'}, {'title': '用户', 'link': reverse_lazy('admin:auth_user_changelist'), 'icon': 'group'}, {'title': '用户组', 'link': reverse_lazy('admin:auth_group_changelist'), 'icon': 'groups'}]},
            {'title': '外部工具', 'separator': True, 'items': [{'title': 'Label Studio', 'link': config("LABEL_STUDIO_PUBLIC_URL", default="http://localhost:8081"), 'icon': 'launch', 'target': '_blank'}]}
        ],
    },
}

# --- Crispy Forms Configuration ---
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"