"""
Autenticación JWT para WebSockets (contenedor `websocket`).

El navegador no puede enviar cabeceras en el handshake de WebSocket, así que el
token viaja en el query string y se valida aquí, antes de aceptar la conexión.
"""

from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser

from src.shared.infrastructure.logging import get_logger

logger = get_logger("realtime.auth")


@database_sync_to_async
def _user_from_token(raw_token: str):
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    from src.modules.accounts.infrastructure.models import User

    try:
        token = AccessToken(raw_token)
        user = User.objects.select_related("company").get(id=token["user_id"])
    except (TokenError, KeyError, User.DoesNotExist, ValueError):
        return AnonymousUser()

    if not user.is_active:
        return AnonymousUser()
    return user


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]

        if not token:
            # Alternativa: subprotocolo `bearer, <token>` para clientes que lo soporten.
            for header, value in scope.get("headers", []):
                if header == b"sec-websocket-protocol":
                    parts = value.decode().split(",")
                    if len(parts) == 2 and parts[0].strip().lower() == "bearer":
                        token = parts[1].strip()
                    break

        scope["user"] = await _user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):  # noqa: N802 - convención de Channels
    return JWTAuthMiddleware(inner)
