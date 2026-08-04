# ─────────────────────────────────────────────────────────────
#  Backend · Django 5 + DRF + Celery + Channels
#  Etapas:  base → development | production | ingest
# ─────────────────────────────────────────────────────────────

# ============ BASE ==========================================
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libmagic1 \
        curl \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ /app/requirements/
RUN pip install --upgrade pip && pip install -r requirements/base.txt

# Usuario sin privilegios
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && mkdir -p /app/media /app/indices /app/staticfiles /app/tmp \
    && chown -R appuser:appuser /app

# ============ DEVELOPMENT ===================================
FROM base AS development

RUN pip install -r requirements/dev.txt && pip install -r requirements/ai.txt

COPY --chown=appuser:appuser . /app/
USER appuser
EXPOSE 8000 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/live || exit 1

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ============ PRODUCTION ====================================
FROM base AS production

RUN pip install -r requirements/prod.txt && pip install -r requirements/ai.txt

COPY --chown=appuser:appuser . /app/
RUN python -c "import compileall; compileall.compile_dir('/app/src', quiet=1)" || true

USER appuser
EXPOSE 8000 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/live || exit 1

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "4", "--worker-class", "gthread", "--threads", "4", "--timeout", "120"]

# ============ INGEST (ffmpeg + Whisper) =====================
# Imagen especializada para la cola `ingest`: transcripción y
# extracción de documentos. Solo esta etapa carga ffmpeg y los
# modelos pesados, manteniendo livianas las demás.
FROM base AS ingest

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        tesseract-ocr \
        tesseract-ocr-spa \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -r requirements/ai.txt && pip install -r requirements/prod.txt

# Caché de modelos de Whisper dentro de la imagen/volumen
ENV HF_HOME=/app/.cache/huggingface \
    XDG_CACHE_HOME=/app/.cache
RUN mkdir -p /app/.cache && chown -R appuser:appuser /app/.cache

COPY --chown=appuser:appuser . /app/
USER appuser

CMD ["celery", "-A", "config", "worker", "-Q", "ingest", "-l", "info", "--concurrency=2"]
