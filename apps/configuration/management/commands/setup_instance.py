import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Performs one-time initialization for a new Visify Story Studio instance.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Starting Visify Story Studio instance setup..."))
        self._create_django_superuser()
        self.stdout.write(self.style.SUCCESS("✅✅✅ Instance setup completed successfully! ✅✅✅"))
        self.stdout.write("You can now log in using the username and password you provided.")

    def _create_django_superuser(self):
        self.stdout.write("🔑 Creating/updating local Django superuser...")
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        if not email or not password:
            raise CommandError("Error: DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD must be set in .env file.")

        try:
            user, created = User.objects.update_or_create(
                username=email,
                defaults={'email': email, 'is_staff': True, 'is_superuser': True}
            )
            user.set_password(password)
            user.save()

            if created:
                self.stdout.write(self.style.SUCCESS(f"Local Django superuser '{email}' created."))
            else:
                self.stdout.write(
                    self.style.WARNING(f"Local Django superuser '{email}' already existed, password has been reset."))
        except Exception as e:
            raise CommandError(f"Error creating/updating local Django superuser: {e}")