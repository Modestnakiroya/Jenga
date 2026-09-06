from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus
import os
import sys

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env", override=True)


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# Set a unique random value in Render (Environment > SECRET_KEY). Never commit a production secret.
SECRET_KEY = os.environ["SECRET_KEY"]

# Read from the environment; default is production-safe False. Local .env should set DEBUG=True.
DEBUG = os.environ.get("DEBUG", "False") == "True"

# Comma-separated hosts. After the first Render deploy, add the service hostname
# (for example jenga.onrender.com) to ALLOWED_HOSTS in the Render dashboard.
ALLOWED_HOSTS = [item.strip() for item in os.environ.get("ALLOWED_HOSTS", "").split(",") if item.strip()]
_render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.accounts.apps.AccountsConfig",
    "apps.transactions.apps.TransactionsConfig",
    "apps.goals.apps.GoalsConfig",
    "apps.retirement.apps.RetirementConfig",
    "apps.planning.apps.PlanningConfig",
    "apps.commitments.apps.CommitmentsConfig",
    "apps.assistant.apps.AssistantConfig",
    "apps.insights.apps.InsightsConfig",
    "apps.sms_gateway.apps.SmsGatewayConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"

def _local_database_url():
    """Same local PostgreSQL this project already uses, as a URL for dj_database_url."""
    user = quote_plus(os.getenv("DB_USER") or "postgres")
    password = quote_plus(os.getenv("DB_PASSWORD") or "")
    host = os.getenv("DB_HOST") or "localhost"
    port = os.getenv("DB_PORT") or "5432"
    name = os.getenv("DB_NAME") or "jenga"
    return f"postgres://{user}:{password}@{host}:{port}/{name}"


# Render sets DATABASE_URL when Postgres is attached. Local .env has no DATABASE_URL,
# so this falls back to the existing local PostgreSQL connection.
DATABASES = {
    "default": dj_database_url.config(
        default=_local_database_url(),
        conn_max_age=600,
        ssl_require=bool(os.getenv("DATABASE_URL") or os.getenv("RENDER")),
    )
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Django 5.2 replacement for STATICFILES_STORAGE = CompressedManifestStaticFilesStorage.
# Tests and local DEBUG keep Django's default storage so collectstatic/manifest files are not required.
_static_backend = "whitenoise.storage.CompressedManifestStaticFilesStorage"
if DEBUG or "test" in sys.argv:
    _static_backend = "django.contrib.staticfiles.storage.StaticFilesStorage"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": _static_backend,
    },
}

if os.getenv("RENDER"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if _render_host:
    _render_origin = f"https://{_render_host}"
    if _render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_render_origin)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
}

SIMPLE_JWT = {
    "CHECK_REVOKE_TOKEN": True,
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.PhoneTokenObtainPairSerializer",
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}


CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", default=False)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

AT_USERNAME = os.getenv("AT_USERNAME", "")
AT_API_KEY = os.getenv("AT_API_KEY", "")

SUNBIRD_API_TOKEN = os.getenv("SUNBIRD_API_TOKEN", "")
SUNBIRD_TRANSLATE_URL = os.getenv(
    "SUNBIRD_TRANSLATE_URL",
    "https://api.sunbird.ai/tasks/nllb_translate",
)

LOGOUT_REDIRECT_URL = "/"
