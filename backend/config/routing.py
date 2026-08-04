"""Rutas WebSocket · usadas únicamente por el contenedor `websocket`."""

from django.urls import path

from src.modules.realtime.consumers import (
    ChatConsumer,
    MaterialStatusConsumer,
    NotificationConsumer,
    PingConsumer,
)

websocket_urlpatterns = [
    path("ws/ping/", PingConsumer.as_asgi()),
    path("ws/materials/<uuid:material_id>/", MaterialStatusConsumer.as_asgi()),
    path("ws/chat/<uuid:session_id>/", ChatConsumer.as_asgi()),
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
