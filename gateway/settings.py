import os
from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.getenv("APP_ENV_FILE", str(BASE_DIR / ".env")))
ON_VERCEL = os.getenv("VERCEL") == "1"
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
if ON_VERCEL and DEBUG:
    raise ImproperlyConfigured("DEBUG must be false on Vercel.")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
missing_keys = [name for name in ("DJANGO_SECRET_KEY", "TOKEN_ENCRYPTION_KEY") if not os.getenv(name)]
if missing_keys:
    raise ImproperlyConfigured(
        f"Missing environment variables: {', '.join(missing_keys)}. "
        "Set them in Vercel Project Settings > Environment Variables for the "
        "deployment's environment, then redeploy. Locally, run scripts/setup_local.py."
    )
try:
    Fernet(TOKEN_ENCRYPTION_KEY.encode())
except (ValueError, TypeError):
    raise ImproperlyConfigured("TOKEN_ENCRYPTION_KEY must be a valid Fernet key.") from None
vercel_host = os.getenv("VERCEL_URL", "")
default_url = f"https://{vercel_host}" if ON_VERCEL and vercel_host else "http://127.0.0.1:8000"
APP_BASE_URL = os.getenv("APP_BASE_URL", default_url).rstrip("/")
if not DEBUG and urlparse(APP_BASE_URL).scheme != "https":
    raise ImproperlyConfigured("APP_BASE_URL must use HTTPS in production.")
app_host = urlparse(APP_BASE_URL).hostname
if not app_host:
    raise ImproperlyConfigured("APP_BASE_URL must include a hostname.")
ALLOWED_HOSTS = [host.strip() for host in os.getenv(
    "ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else app_host,
).split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [APP_BASE_URL]
if ON_VERCEL:
    if vercel_host:
        ALLOWED_HOSTS.append(vercel_host)
        CSRF_TRUSTED_ORIGINS.append(f"https://{vercel_host}")
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CURLEC_KEY_ID = os.getenv("CURLEC_KEY_ID", "")
CURLEC_KEY_SECRET = os.getenv("CURLEC_KEY_SECRET", "")
CURLEC_WEBHOOK_SECRET = os.getenv("CURLEC_WEBHOOK_SECRET", "")
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "axes", "shop",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
    "shop.middleware.PrivateResponseMiddleware",
]
ROOT_URLCONF = "gateway.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "gateway.wsgi.application"
DATABASE_SCHEMA = os.getenv("DATABASE_SCHEMA", "")
database_url = os.getenv("DATABASE_URL", "")
if database_url:
    if urlparse(database_url).scheme not in ("postgres", "postgresql"):
        raise ImproperlyConfigured("DATABASE_URL must be a PostgreSQL connection URL.")
    database = dj_database_url.parse(database_url, conn_max_age=0, conn_health_checks=True)
    database["DISABLE_SERVER_SIDE_CURSORS"] = True  # Compatible with transaction poolers.
    database.setdefault("OPTIONS", {})["prepare_threshold"] = None  # Supabase transaction pooler.
    if ON_VERCEL:
        options = database.setdefault("OPTIONS", {})
        options.setdefault("sslmode", "require")
        if options["sslmode"] not in ("require", "verify-ca", "verify-full"):
            raise ImproperlyConfigured("The Vercel database connection must require TLS.")
    DATABASES = {"default": database}
elif ON_VERCEL:
    raise ImproperlyConfigured(
        "DATABASE_URL is required on Vercel. Connect a PostgreSQL database through "
        "Storage; local SQLite cannot persist payment or token data on Vercel."
    )
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("SQLITE_PATH", str(BASE_DIR / "gateway.sqlite3")),
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_RESET_ON_SUCCESS = True
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Kuala_Lumpur"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 262144
