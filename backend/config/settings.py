import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-fallback-key-change-in-production")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "django_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS": [],
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/dutchkem_trader").split("/")[-1],
        "USER": os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/dutchkem_trader").split("/")[-2].split(":")[0] if ":" in os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/dutchkem_trader").split("/")[-2] else "postgres",
        "PASSWORD": os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/dutchkem_trader").split("/")[-2].split(":")[1] if ":" in os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/dutchkem_trader").split("/")[-2] else "postgres",
        "HOST": os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/dutchkem_trader").split("//")[-1].split(":")[0].split("@")[-1] if "@" in os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/dutchkem_trader").split("//")[-1] else "localhost",
        "PORT": os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/dutchkem_trader").split(":")[-1].split("/")[0] if ":" in os.getenv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/dutchkem_trader").split("//")[-1] else "5432",
    }
}

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}
