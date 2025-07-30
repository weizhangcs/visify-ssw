import os
from celery import Celery

# 设置 Django 的 settings 模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'visify_ssw.settings')

app = Celery('visify_ssw')

# 从 Django 的 settings 中加载配置
app.config_from_object('django.conf:settings', namespace='CELERY')

# 使用无参数的标准自动发现。
# 具体的任务模块将由 settings.py 中的 CELERY_IMPORTS 指定。
app.autodiscover_tasks()