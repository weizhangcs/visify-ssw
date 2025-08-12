# 文件路径: apps/configuration/models.py

from django.db import models
from solo.models import SingletonModel
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

class IntegrationSettings(SingletonModel):
    """
    一个单例模型，用于集中管理所有与外部服务集成相关的、需要在部署后配置的数据。
    """
    # --- Superuser Acls ---
    superuser_emails = models.TextField(
        blank=True, verbose_name="超级管理员邮箱列表",
        help_text="用户首次通过 OIDC 登录时，如果其邮箱在此列表内，将自动被提升为超级管理员。每行一个邮箱地址。"
    )

    def clean(self):
        super().clean()
        emails = self.superuser_emails.splitlines()
        for email in emails:
            if email.strip():
                try:
                    validate_email(email.strip())
                except ValidationError:
                    raise ValidationError(f"'{email}' 不是一个有效的邮箱地址。")

    def get_superuser_emails_as_list(self):
        return [email.strip().lower() for email in self.superuser_emails.splitlines() if email.strip()]

    def __str__(self):
        return "集成设置"

    class Meta:
        verbose_name = "集成设置"