# 文件路径: apps/configuration/models.py

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from model_utils.models import TimeStampedModel
from solo.models import SingletonModel


class IntegrationSettings(SingletonModel):
    """
    一个单例模型，用于集中管理所有与外部服务集成相关的、需要在部署后配置的数据。
    """

    # --- Superuser Acls ---
    superuser_emails = models.TextField(
        blank=True, verbose_name="超级管理员邮箱列表", help_text="用户首次通过 OIDC 登录时，如果其邮箱在此列表内，将自动被提升为超级管理员。每行一个邮箱地址。"
    )

    # --- [新增字段组 1] Cloud API Settings ---
    cloud_api_base_url = models.URLField(max_length=1024, blank=True, null=True, verbose_name="云端 API Base URL")
    cloud_instance_id = models.CharField(max_length=255, blank=True, null=True, verbose_name="云端实例 ID")
    cloud_api_key = models.CharField(max_length=255, blank=True, null=True, verbose_name="云端 API 密钥")

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


class EncodingProfile(TimeStampedModel):
    """
    一个具体的编码配置模板。
    """

    name = models.CharField(max_length=255, unique=True, verbose_name="配置名称", help_text="例如：H.264 1080p (5Mbps)")
    description = models.TextField(blank=True, null=True, verbose_name="描述")
    container = models.CharField(max_length=10, default="mp4", verbose_name="输出容器格式", help_text="例如：mp4, mov")
    ffmpeg_command = models.TextField(
        verbose_name="FFmpeg 参数模板",
        help_text="使用 {input_path} 和 {output_path} 作为占位符。" "例如：-c:v libx264 -b:v 5M -vf scale=-2:1080 -preset fast",
    )

    is_default = models.BooleanField(
        default=False, verbose_name="设为默认", help_text="勾选此项，在启动转码项目时将默认选中此配置。系统中只能有一个默认配置。"
    )

    def save(self, *args, **kwargs):
        """
        重写 save 方法以确保只有一个 profile 是默认的。
        """
        # 如果当前实例被设置为默认
        if self.is_default:
            # 将所有其他实例的 is_default 字段更新为 False
            # .exclude(pk=self.pk) 确保我们不会取消当前实例的勾选
            EncodingProfile.objects.exclude(pk=self.pk).update(is_default=False)

        # 调用父类的 save 方法，正常保存当前实例
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "编码配置"
        verbose_name_plural = "编码配置"
        ordering = ["-created"]
