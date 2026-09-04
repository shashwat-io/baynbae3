"""
Bay'n Bae storefront settings.

Everything secret or environment-specific is read from the environment (a
local .env file is loaded if present). Money is integer rupees everywhere;
paise conversion happens only inside orders.razorpay_gateway.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import dotenv_values

BASE_DIR = Path(__file__).resolve().parent.parent

# Values from .env fill in anything missing or blank in the process environment.
# (Plain load_dotenv never overrides an existing variable, and the dev server's
# autoreloader hands its children the parent's environment, so editing .env
# would otherwise not take effect until a full restart.)
for _key, _value in dotenv_values(BASE_DIR / ".env").items():
    if _value is not None and not os.environ.get(_key):
        os.environ[_key] = _value


def env(name, default=None):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def env_bool(name, default=False):
    return str(env(name, default)).strip().lower() in {"1", "true", "yes", "on"}


SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is not set. Copy .env.example to .env and fill it in "
        "(see README.md)."
    )

DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
CSRF_TRUSTED_ORIGINS = [SITE_URL] if SITE_URL.startswith("http") else []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    "catalog",
    "orders",
    "support",
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

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "catalog.context_processors.storefront",
                "orders.context_processors.bag",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # a bag survives two weeks
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# ---------------------------------------------------------------- storefront
STORE = {
    "name": "Bay'n Bae",
    "tagline": "Resort wear for the ones who never quite left the beach.",
    "instagram": env("INSTAGRAM_HANDLE", "baynbae"),
    "support_email": env("SUPPORT_EMAIL", "hello@baynbae.in"),
    "support_whatsapp": env("SUPPORT_WHATSAPP", ""),
    "free_shipping_over_inr": 1999,
    "shipping_flat_inr": 79,
    "dispatch_days": "2–4 working days",
}

# ------------------------------------------------------------------ razorpay
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", "")
if not DEBUG:
    # Outside development every Razorpay secret is mandatory. A missing key
    # must stop the process, never silently switch the shop to sandbox mode.
    for _name in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"):
        if not env(_name):
            raise ImproperlyConfigured(
                f"{_name} is not set. Razorpay keys are required when DEBUG is false "
                "(see README.md)."
            )
# With DEBUG on and no keys configured, the checkout uses a local sandbox
# payment page so the flow can be walked end to end. Never true in production
# and never true when real keys are present.
RAZORPAY_SANDBOX = DEBUG and not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)

# Unpaid orders older than this are marked abandoned by `manage.py expire_orders`.
ORDER_EXPIRY_MINUTES = 60

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"orders": {"level": "INFO"}},
}
