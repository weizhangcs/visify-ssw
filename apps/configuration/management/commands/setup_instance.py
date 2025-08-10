import os
import time
import requests
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from apps.configuration.models import IntegrationSettings

# --- Constants ---
VSS_DJANGO_APP_NAME = "VSS Workbench (Django)"
VSS_OAUTH_PROVIDER_NAME = "VSS Workbench OIDC Provider"
DEFAULT_AUTH_FLOW_SLUG = "default-provider-authorization-explicit-consent"
DEFAULT_INVALIDATION_FLOW_SLUG = "default-provider-invalidation-flow"
REQUIRED_PROPERTY_MAPPING_NAMES = [
    "authentik default OAuth Mapping: OpenID 'openid'",
    "authentik default OAuth Mapping: OpenID 'email'",
    "authentik default OAuth Mapping: OpenID 'profile'",
]
DEFAULT_SIGNING_KEY_NAME = "authentik Self-signed Certificate"

class Command(BaseCommand):
    help = 'Performs one-time initialization for a new Visify Story Studio instance.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Starting Visify Story Studio instance setup..."))
        self._create_django_superuser()
        self._configure_authentik_and_create_user()
        self.stdout.write(self.style.SUCCESS("✅✅✅ Instance setup completed successfully! ✅✅✅"))
        self.stdout.write("You can now log in using the SSO flow.")

    def _create_django_superuser(self, *args, **kwargs):
        self.stdout.write("🔑 Creating/updating local Django superuser...")
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        if not email or not password:
            raise CommandError("Error: DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD must be set.")
        try:
            user, created = User.objects.update_or_create(username=email, defaults={'email': email, 'is_staff': True,
                                                                                    'is_superuser': True})
            user.set_password(password)
            user.save()
            if created:
                self.stdout.write(self.style.SUCCESS(f"Local Django superuser '{email}' created."))
            else:
                self.stdout.write(self.style.WARNING(f"Local Django superuser '{email}' existed, password reset."))
        except Exception as e:
            raise CommandError(f"Error with local Django superuser: {e}")

    def _configure_authentik_and_create_user(self, *args, **kwargs):
        self.stdout.write("🔗 Configuring Authentik and creating initial SSO user...")
        try:
            api_token = os.environ['AUTHENTIK_API_TOKEN']
            email = os.environ['DJANGO_SUPERUSER_EMAIL']
            password = os.environ['DJANGO_SUPERUSER_PASSWORD']
            authentik_api_url = "http://authentik-server:9000/api/v3"
            public_endpoint = os.environ['PUBLIC_ENDPOINT']
        except KeyError as e:
            raise CommandError(f"Error: Missing required environment variable '{e.name}'.")
        headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
        try:
            application_slug = self._find_or_create_app(authentik_api_url, headers)
            oidc_credentials = self._find_or_create_provider(authentik_api_url, headers, application_slug,
                                                             public_endpoint)
            self._update_integration_settings(oidc_credentials)
            self._create_authentik_user(authentik_api_url, headers, email, password)
        except Exception as e:
            raise CommandError(f"An unexpected error occurred during Authentik configuration: {e}")

    def _create_authentik_user(self, api_url, headers, email, password):
        user_url = f"{api_url}/core/users/"
        params = {'username': email}
        response = requests.get(user_url, headers=headers, params=params)
        response.raise_for_status()
        results = response.json()['results']
        user_pk = None
        if results:
            user_pk = results[0]['pk']
            self.stdout.write(self.style.WARNING(f"Found existing user '{email}' in Authentik."))
        else:
            self.stdout.write(f"Creating user '{email}' in Authentik...")
            payload = {"username": email, "name": email.split('@')[0], "email": email, "is_active": True}
            response = requests.post(user_url, headers=headers, json=payload)
            response.raise_for_status()
            user_pk = response.json()['pk']
            self.stdout.write(self.style.SUCCESS("Authentik user created successfully."))
        self.stdout.write(f"Setting password for Authentik user '{email}'...")
        set_password_url = f"{api_url}/core/users/{user_pk}/set_password/"
        password_payload = {"password": password}
        response = requests.post(set_password_url, headers=headers, json=password_payload)
        response.raise_for_status()
        self.stdout.write(self.style.SUCCESS("Password set successfully in Authentik."))

    def _find_or_create_app(self, api_url, headers):
        app_url = f"{api_url}/core/applications/"
        response = requests.get(app_url, headers=headers, params={'name': VSS_DJANGO_APP_NAME})
        response.raise_for_status()
        data = response.json()
        if data['results']:
            app_slug = data['results'][0]['slug']
            self.stdout.write(self.style.WARNING(f"Found existing App '{VSS_DJANGO_APP_NAME}'."))
            return app_slug
        self.stdout.write(f"Creating App '{VSS_DJANGO_APP_NAME}'...")
        payload = {"name": VSS_DJANGO_APP_NAME, "slug": "vss-workbench-django"}
        response = requests.post(app_url, headers=headers, json=payload)
        response.raise_for_status()
        app_slug = response.json()['slug']
        self.stdout.write(self.style.SUCCESS("App created."))
        return app_slug

    def _find_or_create_provider(self, api_url, headers, app_slug, public_endpoint):
        provider_url = f"{api_url}/providers/oauth2/"
        response = requests.get(provider_url, headers=headers, params={'name': VSS_OAUTH_PROVIDER_NAME})
        response.raise_for_status()
        data = response.json()
        if data['results']:
            provider = data['results'][0]
            self.stdout.write(self.style.WARNING(f"Found existing OIDC Provider '{VSS_OAUTH_PROVIDER_NAME}'."))
            return {'client_id': provider['client_id'], 'client_secret': None}

        self.stdout.write("Dynamically fetching dependencies from Authentik...")

        def get_pk_by_slug(endpoint, slug):
            url = f"{api_url}/{endpoint}/{slug}/";
            res = requests.get(url, headers=headers);
            res.raise_for_status();
            return res.json()['pk']

        def get_property_mapping_pks(names):
            url = f"{api_url}/propertymappings/all/"
            for attempt in range(1, 6):
                res = requests.get(url, headers=headers);
                res.raise_for_status()
                all_mappings = res.json()['results']
                pks_temp = [next((m['pk'] for m in all_mappings if m['name'] == name), None) for name in names]
                if all(pks_temp):
                    self.stdout.write(self.style.SUCCESS("All property mappings found."))
                    return pks_temp
                if attempt < 5:
                    self.stdout.write(
                        self.style.WARNING(f"Mappings not yet available. Retrying in 5s... ({attempt}/5)"))
                    time.sleep(5)
            raise CommandError("Could not find all required property mappings after multiple attempts.")

            # --- [最终修正: 动态获取签名密钥的PK] ---

        def get_signing_key_pk(name):
            url = f"{api_url}/crypto/certificatekeypairs/"
            params = {'name': name}
            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()
            results = res.json()['results']
            if not results:
                raise CommandError(f"Could not find default signing key with name '{name}'.")
            return results[0]['pk']

        auth_flow_pk = get_pk_by_slug("flows/instances", DEFAULT_AUTH_FLOW_SLUG)
        invalidation_flow_pk = get_pk_by_slug("flows/instances", DEFAULT_INVALIDATION_FLOW_SLUG)
        property_mapping_pks = get_property_mapping_pks(REQUIRED_PROPERTY_MAPPING_NAMES)
        signing_key_pk = get_signing_key_pk(DEFAULT_SIGNING_KEY_NAME)

        self.stdout.write(self.style.SUCCESS("Successfully fetched all required dependencies."))

        self.stdout.write(f"Creating OIDC Provider '{VSS_OAUTH_PROVIDER_NAME}'...")
        payload = {
            "name": VSS_OAUTH_PROVIDER_NAME,
            "authorization_flow": auth_flow_pk,
            "invalidation_flow": invalidation_flow_pk,
            "client_type": "confidential",
            "redirect_uris": [{"matching_mode":"strict","url":f"{public_endpoint.rstrip('/')}:8000/oidc/callback/"}],
            "signing_key": signing_key_pk,  # <-- 使用动态获取的PK
            "property_mappings": property_mapping_pks,
            "sub_mode": "user_email"
        }
        response = requests.post(provider_url, headers=headers, json=payload)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            self.stdout.write(self.style.ERROR(f"--- AUTHENTIK API ERROR ---\nDetails: {response.json()}"))
            raise e
        provider_data = response.json()
        app_update_url = f"{api_url}/core/applications/{app_slug}/"
        app_update_payload = {"provider": provider_data['pk']}
        patch_response = requests.patch(app_update_url, headers=headers, json=app_update_payload)
        patch_response.raise_for_status()
        self.stdout.write(self.style.SUCCESS("OIDC Provider created and linked."))
        return {'client_id': provider_data['client_id'], 'client_secret': provider_data['client_secret']}

    def _update_integration_settings(self, credentials):
        self.stdout.write("💾 Updating local database with OIDC credentials...")
        settings_instance = IntegrationSettings.get_solo()
        if credentials.get('client_id'): settings_instance.oidc_rp_client_id = credentials['client_id']
        if credentials.get('client_secret'): settings_instance.oidc_rp_client_secret = credentials['client_secret']
        superuser_emails_str = os.environ.get("AUTHORIZED_SUPERUSER_EMAILS", "")
        settings_instance.superuser_emails = "\n".join(superuser_emails_str.split(','))
        settings_instance.save()
        self.stdout.write(self.style.SUCCESS("IntegrationSettings saved to database."))