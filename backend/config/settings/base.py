"""
Configuración base compartida por todos los entornos.

Las variables sensibles y de entorno se leen SIEMPRE desde el ambiente
(nunca se escriben en el repositorio).
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR.parent / ".env", override=False)


# ─────────────────────────────────────────────────────────────
#  Helpers de entorno
# ─────────────────────────────────────────────────────────────
def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return env(key, str(int(default))).lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    try:
        return int(env(key, str(default)))
    except ValueError:
        return default


def env_float(key: str, default: float) -> float:
    try:
        return float(env(key, str(default)))
    except ValueError:
        return default


def env_list(key: str, default: str = "") -> list[str]:
    raw = env(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ─────────────────────────────────────────────────────────────
#  Núcleo
# ─────────────────────────────────────────────────────────────
SECRET_KEY = env("SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Terceros
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "django_celery_beat",
    "django_celery_results",
    "channels",
    # Módulos del dominio (Clean Architecture)
    "src.modules.accounts",
    "src.modules.projects",
    "src.modules.trainings",
    "src.modules.ai",
    "src.modules.assessments",
    "src.modules.analytics",
]

MIDDLEWARE = [
    "src.shared.presentation.middleware.RequestIDMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "src.shared.presentation.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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

# ─────────────────────────────────────────────────────────────
#  Base de datos · PostgreSQL 17
# ─────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "nexora"),
        "USER": env("POSTGRES_USER", "nexora"),
        "PASSWORD": env("POSTGRES_PASSWORD", "nexora"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 10},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# ─────────────────────────────────────────────────────────────
#  Contraseñas · Argon2 (RNF-25)
# ─────────────────────────────────────────────────────────────
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─────────────────────────────────────────────────────────────
#  Internacionalización
# ─────────────────────────────────────────────────────────────
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────────────────────
#  Archivos estáticos y media
# ─────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ─────────────────────────────────────────────────────────────
#  Django REST Framework
# ─────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "src.shared.presentation.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "src.shared.presentation.exception_handler.domain_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        # Habilita los límites por `throttle_scope` de vistas concretas
        # (login, chat IA, generación de exámenes, carga de material).
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "user": "1000/hour",
        "anon": "100/hour",
        "login": "5/min",
        "password_reset": "3/hour",
        "ai_chat": "30/min",
        "ai_generate": "10/hour",
        "upload": "20/hour",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_LIFETIME_MINUTES", 30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_LIFETIME_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": (
        "src.modules.accounts.presentation.serializers.NexoraTokenObtainPairSerializer"
    ),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Nexora · API",
    "DESCRIPTION": (
        "Plataforma de capacitaciones con Inteligencia Artificial. "
        "RAG sobre videos y documentos, tutor virtual y evaluaciones automáticas."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "TAGS": [
        {"name": "Auth", "description": "Autenticación y gestión de la sesión"},
        {"name": "Usuarios", "description": "Administración de usuarios y grupos"},
        {"name": "Proyectos", "description": "Aplicaciones/proyectos de la empresa"},
        {"name": "Capacitaciones", "description": "Cursos, módulos y lecciones"},
        {"name": "Materiales", "description": "Carga y procesamiento de videos y documentos"},
        {"name": "Aprendizaje", "description": "Inscripciones y progreso"},
        {"name": "IA", "description": "Chat RAG, agente tutor y consumo de IA"},
        {"name": "Evaluaciones", "description": "Exámenes, intentos y corrección"},
        {"name": "Analítica", "description": "Reportes y estadísticas"},
    ],
}

# ─────────────────────────────────────────────────────────────
#  CORS / CSRF
# ─────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")

# ─────────────────────────────────────────────────────────────
#  Celery
# ─────────────────────────────────────────────────────────────
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 60 * 4  # 4 h para videos largos
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 60 * 3
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "ai.ingest_material": {"queue": "ingest"},
    "ai.transcribe_material": {"queue": "ingest"},
    "ai.extract_document": {"queue": "ingest"},
    "ai.embed_chunks": {"queue": "ai"},
    "ai.analyze_material": {"queue": "ai"},
    "ai.rebuild_project_index": {"queue": "ai"},
    "assessments.generate_exam": {"queue": "ai"},
    "assessments.grade_attempt": {"queue": "ai"},
}

# ─────────────────────────────────────────────────────────────
#  Channels · usado por el CONTENEDOR websocket (Daphne)
# ─────────────────────────────────────────────────────────────
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("CHANNEL_LAYERS_URL", "redis://localhost:6379/2")],
            "capacity": 1500,
            "expiry": 60,
        },
    }
}

# ─────────────────────────────────────────────────────────────
#  Cache
# ─────────────────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("CACHE_URL", "redis://localhost:6379/3"),
        "TIMEOUT": 300,
    }
}

# ─────────────────────────────────────────────────────────────
#  Correo
# ─────────────────────────────────────────────────────────────
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@nexora.local")
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173")

# ─────────────────────────────────────────────────────────────
#  IA · Groq es el ÚNICO proveedor externo
# ─────────────────────────────────────────────────────────────
#  Groq resuelve LLM y transcripción (Whisper). Los embeddings se calculan en
#  local con SentenceTransformers y se almacenan en FAISS: no salen de la
#  infraestructura ni requieren una segunda cuenta.
#
#  La clave se lee SOLO de la variable de entorno GROQ_API_KEY. Nunca se
#  escribe en código, imagen ni archivo versionado.
AI_SETTINGS = {
    "GROQ": {
        "API_KEY": env("GROQ_API_KEY"),
        "BASE_URL": env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        # Modelos disponibles en https://console.groq.com/docs/models
        #   llama-3.3-70b-versatile   equilibrio calidad/velocidad (por defecto)
        #   llama-3.1-8b-instant      el más rápido y barato, JSON menos fiable
        #   openai/gpt-oss-120b       mayor calidad de razonamiento, más lento
        "LLM_MODEL": env("GROQ_LLM_MODEL", "llama-3.3-70b-versatile"),
        # Speech-to-Text. `whisper-large-v3` da timestamps por segmento;
        # `whisper-large-v3-turbo` es más rápido y algo menos preciso.
        "WHISPER_MODEL": env("GROQ_WHISPER_MODEL", "whisper-large-v3"),
        "TIMEOUT": env_int("GROQ_TIMEOUT", 120),
        # La API de transcripción sube el audio completo: necesita más margen
        # que una llamada de chat.
        "TRANSCRIBE_TIMEOUT": env_int("GROQ_TRANSCRIBE_TIMEOUT", 600),
    },
    "TEMPERATURE": env_float("LLM_TEMPERATURE", 0.1),
    "MAX_TOKENS": env_int("LLM_MAX_TOKENS", 1024),
    # Longitud del texto que reciben las cadenas de análisis del material.
    # Con modelos pequeños o CPU lenta conviene mantenerlo bajo.
    "ANALYSIS_MAX_CHARS": env_int("AI_ANALYSIS_MAX_CHARS", 6000),
    # Por debajo de esta longitud, el análisis se resuelve en UNA llamada en vez
    # de cuatro. Para un documento de una página divide el tiempo por ~4.
    "COMPACT_ANALYSIS_CHARS": env_int("AI_COMPACT_ANALYSIS_CHARS", 5000),
    # Preguntas por llamada al generar un examen. Pedir muchas de una vez
    # produce un JSON que los modelos pequeños no completan en tiempo razonable.
    "EXAM_BATCH_SIZE": env_int("AI_EXAM_BATCH_SIZE", 2),
}

# ── Embeddings LOCALES (SentenceTransformers) ────────────────
#  Se ejecutan dentro del worker; no hay ninguna llamada externa.
#
#  `multilingual-e5-small` (384 dims) está entrenado para búsqueda ASIMÉTRICA
#  —pregunta corta contra pasaje largo—, que es exactamente lo que hace el RAG.
#  Los modelos `paraphrase-*`, pensados para comparar frases equivalentes, se
#  midieron en este proyecto sobre material de capacitación y confundían el
#  fragmento correcto y dejaban solo 0,009 de margen entre una pregunta
#  respondible y una que no lo está: insuficiente para cualquier umbral.
#
#  E5 exige prefijar el texto ("query:" / "passage:"); sin ellos su calidad cae.
#  Son configurables para poder usar un modelo que no los necesite (déjalos
#  vacíos en ese caso).
#
#  Cambiar de modelo cambia la dimensión del vector y obliga a reconstruir los
#  índices:  python manage.py rebuild_indices
EMBEDDING_SETTINGS = {
    "MODEL": env("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"),
    "DEVICE": env("EMBEDDING_DEVICE", "cpu"),
    "BATCH_SIZE": env_int("EMBEDDING_BATCH_SIZE", 32),
    "QUERY_PREFIX": env("EMBEDDING_QUERY_PREFIX", "query: "),
    "PASSAGE_PREFIX": env("EMBEDDING_PASSAGE_PREFIX", "passage: "),
}

RAG_SETTINGS = {
    "INDEX_ROOT": Path(env("FAISS_INDEX_ROOT", str(BASE_DIR / "indices"))),
    "CHUNK_SIZE_TOKENS": env_int("RAG_CHUNK_SIZE", env_int("CHUNK_SIZE_TOKENS", 800)),
    "CHUNK_OVERLAP_TOKENS": env_int("RAG_CHUNK_OVERLAP", env_int("CHUNK_OVERLAP_TOKENS", 120)),
    "TOP_K": env_int("RAG_TOP_K", env_int("RETRIEVER_TOP_K", 8)),
    # Umbrales de la GroundingPolicy. **Dependen del modelo de embeddings**: la
    # escala de similitud no es comparable entre modelos. E5 comprime los
    # valores hacia arriba (medido sobre material de capacitación: fragmentos
    # relevantes ~0,82-0,89 y consultas ajenas ~0,71-0,81), así que los 0,35 y
    # 0,45 del modelo anterior dejarían pasar cualquier cosa y la IA respondería
    # con contexto irrelevante en vez de admitir que no sabe.
    #
    # Al cambiar EMBEDDING_MODEL hay que recalibrarlos:
    #     python manage.py rag_eval --training <uuid>
    "MIN_SCORE": env_float("RETRIEVER_MIN_SCORE", 0.78),
    "MIN_TOP_SCORE": env_float("RETRIEVER_MIN_TOP_SCORE", 0.82),
    "HYBRID": env_bool("HYBRID_SEARCH_ENABLED", True),
    "EMBED_BATCH_SIZE": 64,
    "MMR_LAMBDA": 0.7,
}

# ─────────────────────────────────────────────────────────────
#  Almacenamiento y límites de carga
# ─────────────────────────────────────────────────────────────
STORAGE_SETTINGS = {
    "BACKEND": env("STORAGE_BACKEND", "local"),
    "MAX_VIDEO_SIZE_MB": env_int("MAX_VIDEO_SIZE_MB", 4096),
    "MAX_DOCUMENT_SIZE_MB": env_int("MAX_DOCUMENT_SIZE_MB", 100),
    "UPLOAD_CHUNK_SIZE_MB": env_int("UPLOAD_CHUNK_SIZE_MB", 5),
    "TMP_DIR": BASE_DIR / "tmp",
}

ALLOWED_UPLOAD_TYPES = {
    "VIDEO": {
        "extensions": {".mp4", ".mov", ".mkv", ".webm", ".avi"},
        "mimes": {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm", "video/x-msvideo"},
    },
    "PDF": {"extensions": {".pdf"}, "mimes": {"application/pdf"}},
    "DOCX": {
        "extensions": {".docx"},
        "mimes": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    },
    "PPTX": {
        "extensions": {".pptx"},
        "mimes": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    },
    "TXT": {"extensions": {".txt"}, "mimes": {"text/plain"}},
    "MD": {"extensions": {".md"}, "mimes": {"text/plain", "text/markdown"}},
    "AUDIO": {
        "extensions": {".mp3", ".wav", ".m4a", ".ogg"},
        "mimes": {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/ogg"},
    },
}

# ─────────────────────────────────────────────────────────────
#  Logging estructurado
# ─────────────────────────────────────────────────────────────
LOG_LEVEL = env("LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
        "json": {
            "()": "src.shared.infrastructure.logging.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "nexora": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
    },
}
