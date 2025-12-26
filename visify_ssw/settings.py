# 文件路径: visify_ssw/settings.py (V4.1 - 修复 AppRegistryNotReady)

"""
Django settings for visify_ssw project.
"""
import logging
import sys
from pathlib import Path

from decouple import config
from django.db import connection  # 导入 connection
from django.urls import reverse_lazy

logger = logging.getLogger(__name__)

# --- [移除顶部的 IntegrationSettings 导入] ---
# 此时 model 尚未定义

# ----------------------------------------------------------------------
# I. 核心/基础配置 (CORE/BASE CONFIGURATION)
# ----------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

# 从 .env 读取基础安全和调试配置
SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)
ALLOWED_HOSTS_str = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1")
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_str.split(",") if host.strip()]

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # --- APP REGISTRY START ---
    "apps.media_assets.apps.MediaAssetsConfig",
    "apps.configuration.apps.ConfigurationConfig",
    "apps.workflow.apps.WorkflowConfig",
    "apps.refinery.apps.RefineryConfig",
    # --- APP REGISTRY END ---
    "corsheaders",
    "solo",
    "crispy_forms",
    "crispy_tailwind",
]

AUTHENTICATION_BACKENDS = ("django.contrib.auth.backends.ModelBackend",)

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "visify_ssw.urls"

# --- LOGGING CONFIGURATION (保持不变) ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",  # Set the handler to process INFO level messages
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {  # Configure the root logger
        "handlers": ["console"],
        "level": "INFO",  # Set the logger to capture INFO level messages
    },
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "visify_ssw.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": "db",
        "PORT": "5432",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ----------------------------------------------------------------------
# III. 动态配置加载 (DYNAMIC CONFIGURATION LOADING)
# ----------------------------------------------------------------------

DYNAMIC_SETTINGS = None
IS_DB_READY = False

# [CRITICAL FIX] 仅在 INSTALLED_APPS 加载后，才尝试导入模型并检查数据库
if "migrate" not in sys.argv and "makemigrations" not in sys.argv:
    try:
        # 1. 导入模型 (在 INSTALLED_APPS 之后是安全的)
        from apps.configuration.models import IntegrationSettings

        # 2. 检查数据库连接是否可用
        if connection.is_usable():
            DYNAMIC_SETTINGS = IntegrationSettings.get_solo()
            IS_DB_READY = True
    except Exception as e:
        # Catching any final errors (like table not found) and fall back to .env
        if "Apps aren't loaded yet" not in str(e):
            logger.warning(f"Failed to load DYNAMIC_SETTINGS from database, falling back to .env: {e}")

# ----------------------------------------------------------------------
# IV. 存储配置 (STORAGE CONFIGURATION)
# ----------------------------------------------------------------------

# 从 .env 读取基础 URL
LOCAL_MEDIA_URL_BASE = config("LOCAL_MEDIA_URL_BASE", default="http://localhost:9999")

# --- 存储后端动态配置 (S3/Local) ---
# DYNAMIC_SETTINGS 可能会是 None，所以使用 getattr 安全访问
FINAL_STORAGE_BACKEND = getattr(DYNAMIC_SETTINGS, "storage_backend", config("STORAGE_BACKEND", default="local"))

# 初始化所有 AWS 凭证变量（如果数据库可用，将被覆盖）
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="")
AWS_S3_CUSTOM_DOMAIN = config("AWS_S3_CUSTOM_DOMAIN", default=None)

# 1. 如果数据库可用，从 DB 加载 AWS 凭证
if IS_DB_READY and FINAL_STORAGE_BACKEND == "s3":
    AWS_ACCESS_KEY_ID = DYNAMIC_SETTINGS.aws_access_key_id
    AWS_SECRET_ACCESS_KEY = DYNAMIC_SETTINGS.aws_secret_access_key
    AWS_STORAGE_BUCKET_NAME = DYNAMIC_SETTINGS.aws_storage_bucket_name
    AWS_S3_REGION_NAME = DYNAMIC_SETTINGS.aws_s3_region_name
    AWS_S3_CUSTOM_DOMAIN = DYNAMIC_SETTINGS.aws_s3_custom_domain

# 2. 应用最终存储设置
if FINAL_STORAGE_BACKEND == "s3":
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    STATICFILES_STORAGE = "storages.backends.s3boto3.S3StaticStorage"

    # 保留用于 S3 路径的前缀配置（这些仍可从 .env 读取）
    AWS_S3_PROCESSED_VIDEOS_PREFIX = config("AWS_S3_PROCESSED_VIDEOS_PREFIX", default="processed_videos/")
    AWS_S3_SOURCE_SUBTITLES_PREFIX = config("AWS_S3_SOURCE_SUBTITLES_PREFIX", default="source_subtitles/")
else:
    # 默认使用本地文件存储
    DEFAULT_FILE_STORAGE = "apps.media_assets.services.storage_backends.EdgeLocalStorage"

# ----------------------------------------------------------------------
# V. 媒体/静态文件路径 (MEDIA/STATIC PATHS)
# ----------------------------------------------------------------------

STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media_root"

# 混排React/Ant Design的引用目录
STATICFILES_DIRS = [
    BASE_DIR / "static_build",
]

# [修改前] 依赖 LOCAL_MEDIA_URL_BASE，导致数据库存储了硬编码的绝对路径
# STATIC_URL = f"{LOCAL_MEDIA_URL_BASE}/static/"
# MEDIA_URL = f"{LOCAL_MEDIA_URL_BASE}/media/"

# 1. 静态文件 (Static): 必须指向 Nginx (9999)，因为它不经过数据库，每次重启由 .env 动态决定，使用绝对路径安全且必要。
STATIC_URL = f"{LOCAL_MEDIA_URL_BASE}/static/"

# 2. 媒体文件 (Media): 保持相对路径，为了让数据库里存的是 "/media/..." 而不是带 IP 的死链。
MEDIA_URL = "/media/"

# 保留此变量供业务逻辑代码（如 Models/Services）使用，用于动态拼接完整 URL
LOCAL_MEDIA_URL_BASE = config("LOCAL_MEDIA_URL_BASE", default="http://localhost:9999")

# ----------------------------------------------------------------------
# VI. 异步/任务队列 (CELERY/TASKS)
# ----------------------------------------------------------------------

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_IMPORTS = (
    "apps.media_assets.tasks",
    "apps.workflow.transcoding.tasks",
    "apps.workflow.delivery.tasks",
    "apps.workflow.annotation.tasks",
    "apps.workflow.inference.tasks",
    "apps.workflow.creative.tasks",
    "apps.workflow.character_annotation.tasks",
    "apps.workflow.scene_annotation.tasks",
    "apps.refinery.tasks",
    "apps.workflow.common.tasks",
)

# 定义队列
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES = {
    "default": {
        "exchange": "default",
        "routing_key": "default",
    },
    "media_queue": {
        "exchange": "media_queue",
        "routing_key": "media_queue",
    },
}

# 定义路由规则 (Router)
CELERY_TASK_ROUTES = {
    # 1. 媒体处理任务 -> media_queue
    "apps.workflow.transcoding.tasks.run_transcoding_job": {"queue": "media_queue"},
    "apps.workflow.transcoding.tasks.generate_waveform": {"queue": "media_queue"},
    "apps.workflow.creative.tasks.start_synthesis_task": {"queue": "media_queue"},
    "apps.workflow.creative.tasks.finalize_synthesis_task": {"queue": "media_queue"},
    "apps.refinery.tasks.refinery_probe_task": {"queue": "media_queue"},
    "apps.refinery.tasks.refinery_transcode_task": {"queue": "media_queue"},
    # 2. 预标注 - 切片与上传 (将来实现) -> media_queue
    "apps.media_assets.tasks.slice_and_upload_task": {"queue": "media_queue"},
    # 3. 其他所有任务 (Cloud API请求、回调处理、DB操作) -> 默认走 default 队列
    "*": {"queue": "default"},
}

# ----------------------------------------------------------------------
# VII. 外部集成服务 URL/TOKEN (EXTERNAL INTEGRATION SERVICES)
# ----------------------------------------------------------------------

# 从 .env 读取内部组件 URL (这些不应该放在 DB 中)
SUBEDITOR_URL = config("SUBEDITOR_URL", default="http://subeditor:3000")
LABEL_STUDIO_URL = config("LABEL_STUDIO_INTERNAL_URL", default="http://label-studio:8080")

# 从 .env 读取派生公共 URL (这些仍由 init_setup.sh 管理)
LABEL_STUDIO_PUBLIC_URL = config("LABEL_STUDIO_PUBLIC_URL", default="http://localhost:8081")
SUBEDITOR_PUBLIC_URL = config("SUBEDITOR_PUBLIC_URL", default="http://localhost:3000")

# --- 云端 API 设置 (从 DB 加载，.env 仅作回退) ---
CLOUD_API_BASE_URL = getattr(DYNAMIC_SETTINGS, "cloud_api_base_url", None) or config("CLOUD_API_BASE_URL", default="")
CLOUD_INSTANCE_ID = getattr(DYNAMIC_SETTINGS, "cloud_instance_id", None) or config("CLOUD_INSTANCE_ID", default="")
CLOUD_API_KEY = getattr(DYNAMIC_SETTINGS, "cloud_api_key", None) or config("CLOUD_API_KEY", default="")

# ----------------------------------------------------------------------
# VIII. 其它杂项配置 (MISCELLANEOUS)
# ----------------------------------------------------------------------

# 1. 获取 Django Admin 的实际公共访问 URL
# 确保使用 PUBLIC_ENDPOINT 的 host/scheme 并强制使用 8000 端口
ADMIN_PUBLIC_URL = config("PUBLIC_ENDPOINT", default="http://localhost").rstrip("/") + ":8000"

# 2. CSRF/SESSION 安全修正 (防止在 HTTP 环境下 CSRF 失败)
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

# 3. CSRF 配置
CSRF_TRUSTED_ORIGINS = [
    # 信任 Django Admin 自己的 URL (用于 Admin 表单提交)
    ADMIN_PUBLIC_URL,
    # 信任 Subeditor URL (用于跨域表单提交或嵌入场景)
    config("SUBEDITOR_PUBLIC_URL", default="http://localhost:3000"),
]

CORS_ALLOWED_ORIGINS_str = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000,http://127.0.0.1:3000")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ALLOWED_ORIGINS_str.split(",") if origin.strip()]
CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]
CORS_ALLOW_HEADERS = ["accept", "authorization", "content-type", "user-agent", "x-csrftoken", "x-requested-with"]

# 4. FFmpeg 参数
FFMPEG_VIDEO_BITRATE = config("FFMPEG_VIDEO_BITRATE", default="2M")
FFMPEG_VIDEO_PRESET = config("FFMPEG_VIDEO_PRESET", default="fast")

# ----------------------------------------------------------------------
# IX. ADMIN/UNFOLD 配置 (ADMIN/UNFOLD CONFIGURATION)
# ----------------------------------------------------------------------
UNFOLD = {
    "SITE_TITLE": "Visify Story Studio (Edge)",
    "SIDEBAR": {
        "navigation": [
            {
                "title": "工作台",
                "items": [{"title": "仪表盘", "icon": "space_dashboard", "link": reverse_lazy("admin:index")}],
            },
            {
                "title": "媒资管理",
                "separator": True,
                "items": [
                    {
                        "title": "内容资产",
                        "link": reverse_lazy("admin:media_assets_asset_changelist"),
                        "icon": "video_library",
                    },
                    {"title": "媒体文件", "link": reverse_lazy("admin:media_assets_media_changelist"), "icon": "movie"},
                ],
            },
            {
                "title": "视频预处理",
                "separator": True,
                "items": [
                    {
                        "title": "转码项目",
                        "icon": "movie_filter",
                        "link": reverse_lazy("admin:workflow_transcodingproject_changelist"),
                    },
                    {
                        "title": "角色标注项目",  # Character Annotation 入口
                        "icon": "face",
                        "link": reverse_lazy("admin:workflow_characterannotationproject_changelist"),
                    },
                    {
                        "title": "场景标注项目",  # Scene Annotation 入口
                        "icon": "auto_awesome_motion",
                        "link": reverse_lazy("admin:workflow_sceneannotationproject_changelist"),
                    },
                    {
                        "title": "转码任务",
                        "icon": "history",
                        "link": reverse_lazy("admin:workflow_transcodingjob_changelist"),
                    },
                    {
                        "title": "转码配置",
                        "icon": "tune",
                        "link": reverse_lazy("admin:configuration_encodingprofile_changelist"),
                    },
                ],
            },
            {
                "title": "建模工作流",
                "separator": True,
                "items": [
                    {
                        "title": "标注项目",
                        "icon": "rate_review",
                        "link": reverse_lazy("admin:workflow_annotationproject_changelist"),
                    },
                    {
                        "title": "推理项目",
                        "icon": "insights",
                        "link": reverse_lazy("admin:workflow_inferenceproject_changelist"),
                    },
                ],
            },
            {
                "title": "创作工作流",
                "separator": True,
                "items": [
                    {
                        "title": "影视解说二创",
                        "icon": "send",
                        "link": reverse_lazy("admin:workflow_creativeproject_changelist"),
                    },
                ],
            },
            {
                "title": "分发工作流",
                "separator": True,
                "items": [
                    {"title": "分发任务", "icon": "send", "link": reverse_lazy("admin:workflow_deliveryjob_changelist")},
                ],
            },
            {
                "title": "系统设置",
                "separator": True,
                "items": [
                    {
                        "title": "集成设置",
                        "link": reverse_lazy("admin:configuration_integrationsettings_changelist"),
                        "icon": "hub",
                    },
                    {"title": "用户", "link": reverse_lazy("admin:auth_user_changelist"), "icon": "group"},
                    {"title": "用户组", "link": reverse_lazy("admin:auth_group_changelist"), "icon": "groups"},
                ],
            },
        ],
    },
    "TABS": "apps.workflow.tabs.get_global_tabs",
}

# --- Crispy Forms Configuration ---
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"
