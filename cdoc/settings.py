"""
Django settings for cdoc project.

Generated by 'django-admin startproject' using Django 4.0.3.

For more information on this file, see
https://docs.djangoproject.com/en/4.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.0/ref/settings/
"""

from pathlib import Path
import os, dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-uucy+@+8zv&)v&#r&l7)=@3&s%#wn4luos0i&x4@$o7d2*t@3t"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "False") == "True"

DEPLOYMENT_HOST_NAME = os.environ.get("DEPLOYMENT_HOST_NAME", "localhost")

ALLOWED_HOSTS = [
    "localhost",
    "0.0.0.0",
    DEPLOYMENT_HOST_NAME,
]

WEBSITE_HOST = f"https://{DEPLOYMENT_HOST_NAME}"

CSRF_TRUSTED_ORIGINS = [WEBSITE_HOST]

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_extensions",
    "app",
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
]

ROOT_URLCONF = "cdoc.urls"

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

WSGI_APPLICATION = "cdoc.wsgi.application"


# Password validation
# https://docs.djangoproject.com/en/4.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.0/howto/static-files/

STATIC_URL = "static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Default primary key field type
# https://docs.djangoproject.com/en/4.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "color_with_extra": {
            "()": "cdoc.formatter.ExtraFormatter",
            "format": "%(log_color)s[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s][%(name)s:%(lineno)d] %(message)s ",
            "log_colors": {
                "DEBUG": "white",
                "INFO": "cyan",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        },
        "color": {
            "()": "colorlog.ColoredFormatter",
            "format": "%(log_color)s[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s][%(name)s:%(lineno)d] %(message)s ",
            "log_colors": {
                "DEBUG": "white",
                "INFO": "cyan",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        },
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "[%(asctime)s] %(levelname)s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
    },
    "handlers": {
        "console": {  # writes to the console
            "class": "logging.StreamHandler",
            "level": "INFO",
            "filters": ["require_debug_true"],
            "formatter": "color",
        },
        "console_with_extra": {  # writes to the console
            "class": "logging.StreamHandler",
            "level": "INFO",
            "filters": ["require_debug_true"],
            "formatter": "color_with_extra",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "propagate": True,
        },
        "py.warnings": {
            "handlers": ["console"],
            "propagate": True,
        },
        "app": {
            "handlers": ["console_with_extra"],
            "level": "DEBUG",
        },
        "lib": {
            "handlers": ["console_with_extra"],
            "level": "DEBUG",
        },
    },
}

# Database
# https://docs.djangoproject.com/en/4.0/ref/settings/#databases


DATABASES = dict()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES["default"] = dj_database_url.config()
else:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }

APP_AUTH_KEY = os.environ.get("APP_AUTH_KEY")
try:
    from .local_settings import *  # noqa
except ModuleNotFoundError:
    # Local settings not found. Expect the default settings to be set by env variables
    GITHUB_CREDS = {
        # GITHUB APP
        "client_id": os.environ["CDOC_GITHUB_CLIENT_ID"],
        "client_secret": os.environ["CDOC_GITHUB_CLIENT_SECRET"],
        "app_id": os.environ["CDOC_GITHUB_APP_ID"],
    }

    if "CDOC_SENTRY_DSN" in os.environ:
        import sentry_sdk  # noqa
        from sentry_sdk.integrations.django import DjangoIntegration  # noqa

        sentry_sdk.init(
            dsn=os.environ["CDOC_SENTRY_DSN"],
            integrations=[DjangoIntegration()],
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            # We recommend adjusting this value in production.
            traces_sample_rate=1.0,
            # If you wish to associate users to errors (assuming you are using
            # django.contrib.auth) you may enable sending PII data.
            send_default_pii=True,
        )
