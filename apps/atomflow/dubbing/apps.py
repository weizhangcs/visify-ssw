from django.apps import AppConfig


class DubbingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.atomflow.dubbing"
    label = "dubbing"
    verbose_name = "Atomflow 配音流水线"
