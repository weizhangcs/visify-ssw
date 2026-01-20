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
    "apps.atomflow.apps.AtomflowConfig",
    "apps.vector",
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

# ----------------------------------------------------------------------
# II. 数据库与国际化 (DATABASE & I18N)
# ----------------------------------------------------------------------

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
# III. 动态配置加载 (DYNAMIC CONFIGURATION)
# ----------------------------------------------------------------------

DYNAMIC_SETTINGS = None
IS_DB_READY = False

# 仅在 INSTALLED_APPS 加载后，才尝试导入模型并检查数据库 (防止迁移时报错)
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

# ----------------------------------------------------------------------
# V. 媒体/静态文件路径 (MEDIA/STATIC PATHS)
# ----------------------------------------------------------------------

STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media_root"

# React/Ant Design 构建产物目录
STATICFILES_DIRS = [
    BASE_DIR / "static_build",
]

# 保留此变量供业务逻辑代码（如 Models/Services）使用，用于动态拼接完整 URL
LOCAL_MEDIA_URL_BASE = config("LOCAL_MEDIA_URL_BASE", default="http://localhost:9999")

# 1. 静态文件 (Static): 必须指向 Nginx (9999)，因为它不经过数据库，每次重启由 .env 动态决定，使用绝对路径安全且必要。
STATIC_URL = f"{LOCAL_MEDIA_URL_BASE}/static/"

# 2. 媒体文件 (Media): 同样指向 Nginx (9999)，确保 Admin/API 返回的 URL 能直接访问
MEDIA_URL = f"{LOCAL_MEDIA_URL_BASE}/media/"

# ----------------------------------------------------------------------
# VI. 异步/任务队列 (CELERY/TASKS)
# ----------------------------------------------------------------------

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

CELERY_IMPORTS = [
    "apps.media_assets.tasks",
    "apps.workflow.annotation.tasks",
    "apps.workflow.creative.tasks",
    "apps.workflow.common.tasks",
]

# 仅在环境具备 numpy (即 Media Worker) 时加载 Refinery 任务
# 防止 Default Worker 因缺少依赖而启动失败
try:
    import numpy  # noqa: F401

    CELERY_IMPORTS.append("apps.atomflow.refinery.tasks")
except ImportError:
    pass

CELERY_IMPORTS = tuple(CELERY_IMPORTS)

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
    "apps.workflow.creative.tasks.start_synthesis_task": {"queue": "media_queue"},
    "apps.workflow.creative.tasks.finalize_synthesis_task": {"queue": "media_queue"},
    "apps.atomflow.refinery.tasks.execute_step": {"queue": "media_queue"},
    # 3. 其他所有任务 (Cloud API请求、回调处理、DB操作) -> 默认走 default 队列
    "*": {"queue": "default"},
}

# ----------------------------------------------------------------------
# VII. 外部集成服务 URL/TOKEN (EXTERNAL INTEGRATION SERVICES)
# ----------------------------------------------------------------------

# --- 云端 API 设置 (从 DB 加载，.env 仅作回退) ---
CLOUD_API_BASE_URL = getattr(DYNAMIC_SETTINGS, "cloud_api_base_url", None) or config("CLOUD_API_BASE_URL", default="")
CLOUD_INSTANCE_ID = getattr(DYNAMIC_SETTINGS, "cloud_instance_id", None) or config("CLOUD_INSTANCE_ID", default="")
CLOUD_API_KEY = getattr(DYNAMIC_SETTINGS, "cloud_api_key", None) or config("CLOUD_API_KEY", default="")

# ----------------------------------------------------------------------
# VIII. 安全与网络配置 (SECURITY & NETWORK)
# ----------------------------------------------------------------------

# 1. Admin 公共访问 URL
# 确保使用 PUBLIC_ENDPOINT 的 host/scheme 并强制使用 8000 端口
ADMIN_PUBLIC_URL = config("PUBLIC_ENDPOINT", default="http://localhost").rstrip("/") + ":18000"

# 2. CSRF/SESSION 安全修正 (防止在 HTTP 环境下 CSRF 失败)
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

# 3. 禁用 COOP 以避免非 HTTPS 环境下的浏览器警告
# 在非 HTTPS (如 http://10.x.x.x) 环境下，浏览器会忽略 COOP 头并报警告。
# 对于内网 Edge 部署，显式禁用此策略以消除控制台报错。
SECURE_CROSS_ORIGIN_OPENER_POLICY = None

# 3. CSRF 配置
CSRF_TRUSTED_ORIGINS = [
    # 信任 Django Admin 自己的 URL (用于 Admin 表单提交)
    ADMIN_PUBLIC_URL,
]

CORS_ALLOWED_ORIGINS_str = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000,http://127.0.0.1:3000")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ALLOWED_ORIGINS_str.split(",") if origin.strip()]
CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]
CORS_ALLOW_HEADERS = ["accept", "authorization", "content-type", "user-agent", "x-csrftoken", "x-requested-with"]

# ----------------------------------------------------------------------
# IX. 业务参数配置 (BUSINESS CONFIGURATION)
# ----------------------------------------------------------------------

# 1. FFmpeg 参数
FFMPEG_VIDEO_BITRATE = config("FFMPEG_VIDEO_BITRATE", default="2M")
FFMPEG_VIDEO_PRESET = config("FFMPEG_VIDEO_PRESET", default="fast")

# 2. 请求体大小限制 (Request Body Size Limit)
# 默认是 2.5MB。由于 Annotation Workbench 保存时会提交包含 waveform_data (可能很大)
# 和大量 scenes/dialogues 的 JSON，容易超限。此处调整为 50MB。
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB

# ----------------------------------------------------------------------
# X. 管理后台配置 (ADMIN/UNFOLD CONFIGURATION)
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
                        "title": "精炼流水线",
                        "icon": "precision_manufacturing",
                        "link": reverse_lazy("admin:atomflow_refineryatompipeline_changelist"),
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
                        "title": "数据建模",
                        "icon": "library_books",
                        "link": reverse_lazy("admin:vector_vectorsourceasset_changelist"),
                    },
                    {
                        "title": "模型列表",
                        "icon": "memory",
                        "link": reverse_lazy("admin:vector_vectorindex_changelist"),
                    },
                    {
                        "title": "查询模型",
                        "icon": "search",
                        "link": reverse_lazy("vector:vector_search"),
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
                "title": "系统设置",
                "separator": True,
                "items": [
                    {
                        "title": "集成设置",
                        "link": reverse_lazy("admin:configuration_integrationsettings_changelist"),
                        "icon": "hub",
                    },
                    {
                        "title": "转码配置",
                        "icon": "tune",
                        "link": reverse_lazy("admin:configuration_encodingprofile_changelist"),
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
