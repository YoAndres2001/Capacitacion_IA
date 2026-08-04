"""Configuración de producción (RNF-20 a RNF-28)."""

from .base import *  # noqa: F403
from .base import INSTALLED_APPS, LOGGING, MIDDLEWARE, REST_FRAMEWORK, env

DEBUG = False

# ── Seguridad ────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

CORS_ALLOW_ALL_ORIGINS = False

# Solo JSON en producción: sin API navegable.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
}

# ── Observabilidad ───────────────────────────────────────────
INSTALLED_APPS = ["django_prometheus", *INSTALLED_APPS]
MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    *MIDDLEWARE,
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

LOGGING = {
    **LOGGING,
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
}

_sentry_dsn = env("SENTRY_DSN")
if _sentry_dsn:  # pragma: no cover
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment="production",
    )
