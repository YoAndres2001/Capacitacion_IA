"""Configuración para la ejecución de tests."""

from .base import *  # noqa: F403
from .base import BASE_DIR, RAG_SETTINGS

DEBUG = False

# Hash rápido: los tests no necesitan Argon2.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

MEDIA_ROOT = BASE_DIR / "tmp" / "test-media"
RAG_SETTINGS = {**RAG_SETTINGS, "INDEX_ROOT": BASE_DIR / "tmp" / "test-indices"}

# Los tests usan dobles de los puertos de IA; nunca llaman a un proveedor real.
AI_SETTINGS_OVERRIDE_FOR_TESTS = True
