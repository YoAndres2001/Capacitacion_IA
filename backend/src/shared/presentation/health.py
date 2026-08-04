"""Endpoints de salud (RNF-30)."""

from __future__ import annotations

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET


@require_GET
@csrf_exempt
def health_live(request):
    """El proceso está vivo. No toca dependencias externas."""
    return JsonResponse({"status": "ok"})


@require_GET
@csrf_exempt
def health_ready(request):
    """Verifica las dependencias necesarias para atender tráfico."""
    checks: dict[str, str] = {}
    healthy = True

    # PostgreSQL
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover
        checks["database"] = f"error: {exc.__class__.__name__}"
        healthy = False

    # Redis (cache)
    try:
        from django.core.cache import cache

        cache.set("health:ready", "1", 5)
        checks["cache"] = "ok" if cache.get("health:ready") == "1" else "error"
        healthy = healthy and checks["cache"] == "ok"
    except Exception as exc:  # pragma: no cover
        checks["cache"] = f"error: {exc.__class__.__name__}"
        healthy = False

    # Almacenamiento e índices
    try:
        settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        settings.RAG_SETTINGS["INDEX_ROOT"].mkdir(parents=True, exist_ok=True)
        checks["storage"] = "ok"
    except Exception as exc:  # pragma: no cover
        checks["storage"] = f"error: {exc.__class__.__name__}"
        healthy = False

    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=200 if healthy else 503,
    )
