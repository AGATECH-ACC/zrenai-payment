import json
import os
import subprocess
import sys

from cryptography.fernet import Fernet
from django.test import SimpleTestCase


class DeploymentSettingsTests(SimpleTestCase):
    def load_settings(self, **changes):
        env = os.environ.copy()
        for name in (
            "DJANGO_SECRET_KEY", "TOKEN_ENCRYPTION_KEY", "DATABASE_URL",
            "APP_BASE_URL", "ALLOWED_HOSTS", "VERCEL_URL",
        ):
            env.pop(name, None)
        env.update({
            "APP_ENV_FILE": "/nonexistent/zrenai-test-environment",
            "VERCEL": "1", "DEBUG": "false",
            "DJANGO_SECRET_KEY": "test-only-secret",
            "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "APP_BASE_URL": "https://store.example.com",
        })
        env.update(changes)
        return subprocess.run(
            [sys.executable, "-c", (
                "import json; from gateway import settings as s; "
                "print(json.dumps({'engine':s.DATABASES['default']['ENGINE'],"
                "'hosts':s.ALLOWED_HOSTS,'csrf':s.CSRF_TRUSTED_ORIGINS,"
                "'secure':s.SESSION_COOKIE_SECURE,"
                "'proxy':getattr(s,'SECURE_PROXY_SSL_HEADER',None)}))"
            )], env=env, text=True, capture_output=True, timeout=15,
        )

    def test_missing_secret_names_are_actionable(self):
        result = self.load_settings(DJANGO_SECRET_KEY="", TOKEN_ENCRYPTION_KEY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing environment variables: DJANGO_SECRET_KEY, TOKEN_ENCRYPTION_KEY", result.stderr)

    def test_vercel_never_silently_falls_back_to_sqlite(self):
        result = self.load_settings()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL is required on Vercel", result.stderr)

    def test_vercel_rejects_sqlite_url(self):
        result = self.load_settings(DATABASE_URL="sqlite:///tmp/app.sqlite3")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a PostgreSQL", result.stderr)

    def test_vercel_rejects_insecure_database_and_debug(self):
        result = self.load_settings(DATABASE_URL="postgresql://test:test@localhost/db?sslmode=disable")
        self.assertIn("must require TLS", result.stderr)
        self.assertNotEqual(result.returncode, 0)
        result = self.load_settings(DEBUG="true")
        self.assertIn("DEBUG must be false", result.stderr)

    def test_configured_build_import_needs_no_database_connection(self):
        result = self.load_settings(
            DATABASE_URL="postgresql://test:test@localhost/db?sslmode=require",
            VERCEL_URL="deployment.example.vercel.app",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(result.stdout)
        self.assertEqual(settings["engine"], "django.db.backends.postgresql")
        self.assertTrue(settings["secure"])
        self.assertEqual(settings["proxy"], ["HTTP_X_FORWARDED_PROTO", "https"])
        self.assertIn("store.example.com", settings["hosts"])
        self.assertIn("deployment.example.vercel.app", settings["hosts"])
        self.assertIn("https://deployment.example.vercel.app", settings["csrf"])

    def test_invalid_encryption_key_fails_early_without_exposing_value(self):
        result = self.load_settings(TOKEN_ENCRYPTION_KEY="invalid-secret")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be a valid Fernet key", result.stderr)
        self.assertNotIn("invalid-secret", result.stderr)
