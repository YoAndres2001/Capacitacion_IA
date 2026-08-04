"""
Enrutado HTTP del contenedor `backend`.

IMPORTANTE: aquí NO se registran rutas WebSocket. El tiempo real vive en el
contenedor `websocket` (Daphne) y se enruta desde `config/routing.py`.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from src.shared.presentation.health import health_live, health_ready

api_v1 = [
    path("auth/", include("src.modules.accounts.presentation.auth_urls")),
    path("", include("src.modules.accounts.presentation.urls")),
    path("", include("src.modules.projects.presentation.urls")),
    path("", include("src.modules.trainings.presentation.urls")),
    path("", include("src.modules.ai.presentation.urls")),
    path("", include("src.modules.assessments.presentation.urls")),
    path("analytics/", include("src.modules.analytics.presentation.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    # Salud
    path("health/live", health_live, name="health-live"),
    path("health/ready", health_ready, name="health-ready"),
    # API
    path("api/v1/", include((api_v1, "api"), namespace="v1")),
    # Documentación OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
