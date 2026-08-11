"""Configuración de Celery."""

import os

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("nexora")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Descubre `tasks.py` dentro de cada módulo (incluida la ruta infrastructure/).
app.autodiscover_tasks(
    lambda: [
        "src.modules.ai.infrastructure",
        "src.modules.assessments.infrastructure",
        "src.modules.trainings.infrastructure",
        "src.modules.accounts.infrastructure",
    ],
    related_name="tasks",
)


@setup_logging.connect
def configure_logging(*args, **kwargs):  # pragma: no cover
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)


@app.task(bind=True, name="debug.ping")
def debug_ping(self):  # pragma: no cover
    return "pong"
