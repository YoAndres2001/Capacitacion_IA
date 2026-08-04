"""Configuración de desarrollo."""

from importlib.util import find_spec

from .base import *  # noqa: F403
from .base import INSTALLED_APPS, REST_FRAMEWORK

DEBUG = True

# Las imágenes especializadas (p. ej. el worker de ingesta) no instalan las
# dependencias de desarrollo: se agrega solo si está disponible.
if find_spec("django_extensions") is not None:
    INSTALLED_APPS = [*INSTALLED_APPS, "django_extensions"]

# En desarrollo se permite navegar la API desde el navegador.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
}

CORS_ALLOW_ALL_ORIGINS = True

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# Cabeceras de seguridad relajadas: nginx dev no usa TLS.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
