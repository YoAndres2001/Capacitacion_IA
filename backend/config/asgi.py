"""
ASGI · servido por Daphne en el contenedor `websocket` (independiente).

Cumple la restricción del proyecto: el tiempo real no se ejecuta dentro del
contenedor principal de Django.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

# La app HTTP debe construirse antes de importar consumidores (carga de apps).
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from config.routing import websocket_urlpatterns  # noqa: E402
from src.modules.realtime.auth import JWTAuthMiddlewareStack  # noqa: E402

application = ProtocolTypeRouter(
    {
        # El contenedor websocket también responde HTTP para su healthcheck.
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
