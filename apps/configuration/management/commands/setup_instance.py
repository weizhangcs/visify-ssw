# 文件路径: apps/configuration/management/commands/setup_instance.py

import os

from decouple import config
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.atomflow.refinery.models import RefineryAtomRule
from apps.configuration.models import EncodingProfile, IntegrationSettings


class Command(BaseCommand):
    help = "Performs one-time initialization for a new Visify Story Studio instance."

    def add_arguments(self, parser: CommandParser):
        parser.add_argument("--cloud-url", type=str, default=None, help="Cloud API Base URL")
        parser.add_argument("--cloud-id", type=str, default=None, help="Cloud Instance ID")
        parser.add_argument("--cloud-key", type=str, default=None, help="Cloud API Key")

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Starting Visify Story Studio instance setup..."))
        self._create_django_superuser()
        self._create_default_encoding_profile()
        self._create_default_refinery_rule()
        self._update_integration_settings(options)
        self.stdout.write(self.style.SUCCESS("✅✅✅ Instance setup completed successfully! ✅✅✅"))
        self.stdout.write("You can now log in using the username and password you provided.")

    def _create_django_superuser(self):
        # ... (保持原有逻辑不变)
        self.stdout.write("🔑 Creating/updating local Django superuser...")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not email or not password:
            raise CommandError("Error: DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD must be set in .env file.")

        try:
            user, created = User.objects.update_or_create(
                username=email, defaults={"email": email, "is_staff": True, "is_superuser": True}
            )
            user.email = email
            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()

            if created:
                self.stdout.write(self.style.SUCCESS(f"Local Django superuser '{email}' created."))
            else:
                self.stdout.write(
                    self.style.WARNING(f"Local Django superuser '{email}' already existed, password has been reset.")
                )
        except Exception as e:
            raise CommandError(f"Error creating/updating local Django superuser: {e}")

    def _update_integration_settings(self, options):
        """
        [重构] 统一更新 IntegrationSettings 单例模型。
        包含 Label Studio Token 和 Cloud API 配置。
        """
        self.stdout.write("⚙️  Configuring Integration Settings...")

        cloud_url = options.get("cloud_url")
        cloud_id = options.get("cloud_id")
        cloud_key = options.get("cloud_key")

        try:
            # 1. 获取单例对象 (使用原子锁 get_or_create(pk=1))
            settings_obj, created = IntegrationSettings.objects.get_or_create(pk=1, defaults={})

            update_fields = []

            # 2. 理 Cloud API 配置
            # 只有当参数不为空时才更新
            if cloud_url:
                # 简单的清洗，去除末尾斜杠防止 404
                clean_url = cloud_url.strip().rstrip("/")
                settings_obj.cloud_api_base_url = clean_url
                update_fields.append("cloud_api_base_url")
                self.stdout.write(f"- Cloud URL set to: {clean_url}")

            if cloud_id:
                settings_obj.cloud_instance_id = cloud_id.strip()
                update_fields.append("cloud_instance_id")
                self.stdout.write("- Cloud Instance ID set.")

            if cloud_key:
                settings_obj.cloud_api_key = cloud_key.strip()
                update_fields.append("cloud_api_key")
                self.stdout.write("- Cloud API Key set.")

            # 4. 保存变更
            if update_fields:
                settings_obj.save(update_fields=update_fields)
                self.stdout.write(self.style.SUCCESS("✅ Integration Settings updated in database."))
            else:
                self.stdout.write("   - No changes made to Integration Settings.")

        except Exception as e:
            raise CommandError(f"CRASH ERROR: Fatal exception during integration settings update: {e}")

    def _create_default_encoding_profile(self):
        # ... (保持原有逻辑不变)
        self.stdout.write("🎞️ Creating default Encoding Profile for Annotation...")

        name = config("DEFAULT_ENCODING_NAME", "H.264 720p (1Mbps UltraFast)")
        cmd = config("DEFAULT_FFMPEG_CMD", "-c:v libx264 -b:v 1M -vf scale=-2:720 -preset ultrafast")

        if EncodingProfile.objects.filter(is_default=True, name=name).exists():
            self.stdout.write(
                self.style.WARNING("Default Encoding Profile already exists with desired name. Skipping creation.")
            )
            return

        profile, created = EncodingProfile.objects.update_or_create(
            name=name,
            defaults={
                "description": "Automatically generated optimized profile for fast annotation viewing (720p/1Mbps).",
                "container": "mp4",
                "ffmpeg_command": cmd,
                "is_default": True,
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created default Encoding Profile: '{name}'."))
        else:
            self.stdout.write(self.style.WARNING(f"Updated existing Encoding Profile: '{name}' to be the default."))

    def _create_default_refinery_rule(self):
        """
        [新增] 创建默认的 Refinery Pipeline 规则
        """
        self.stdout.write("🛠️  Creating default Refinery Pipeline Rule...")

        rules_json = [
            {"seq": 1, "unit_slug": "transcode", "name": "原子转码", "obligation": "REQUIRED"},
            {"seq": 2, "unit_slug": "probe", "name": "原子探测", "obligation": "REQUIRED", "dependence": [1]},
            {"seq": 3, "unit_slug": "generate_hls", "name": "HLS切片", "obligation": "REQUIRED", "dependence": [1]},
            {"seq": 4, "unit_slug": "text_analyze", "name": "文本分析", "obligation": "REQUIRED", "dependence": [3]},
            {"seq": 5, "unit_slug": "audio_analyze", "name": "声纹分析", "obligation": "REQUIRED", "dependence": [4]},
            {
                "seq": 6,
                "unit_slug": "global_character_refine",
                "name": "全剧角色统筹",
                "obligation": "REQUIRED",
                "dependence": [5],
                "scope": "ASSET",
            },
            {"seq": 7, "unit_slug": "slice", "name": "视觉切片", "obligation": "REQUIRED", "dependence": [6]},
            {"seq": 8, "unit_slug": "frame_extract", "name": "关键帧提取", "obligation": "REQUIRED", "dependence": [7]},
            {"seq": 9, "unit_slug": "frame_probe", "name": "关键帧检测", "obligation": "REQUIRED", "dependence": [8]},
            {"seq": 10, "unit_slug": "synchronize", "name": "云端同步", "obligation": "REQUIRED", "dependence": [9]},
            {"seq": 11, "unit_slug": "analyze_visual", "name": "视觉识别", "obligation": "REQUIRED", "dependence": [10]},
            {"seq": 12, "unit_slug": "analyze_slice", "name": "切片分析", "obligation": "REQUIRED", "dependence": [11]},
            {"seq": 13, "unit_slug": "regroup_slice", "name": "切片聚类", "obligation": "REQUIRED", "dependence": [12]},
        ]

        slug = "default_full_refinery"
        name = "自动化媒资推理"

        try:
            rule, created = RefineryAtomRule.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": "系统默认的全量精炼流程，包含从转码到场景聚类的所有步骤。",
                    "rules_config": rules_json,
                    "mode": "PROD",
                },
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created default Refinery Rule: '{name}'."))
            else:
                self.stdout.write(self.style.WARNING(f"Updated default Refinery Rule: '{name}'."))
        except Exception as e:
            raise CommandError(f"Error creating/updating default Refinery Rule: {e}")
