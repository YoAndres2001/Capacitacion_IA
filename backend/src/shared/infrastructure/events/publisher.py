"""
Publicador de eventos hacia el channel layer de Redis.

Este es el puente entre el contenedor `backend`/workers (que producen eventos)
y el contenedor `websocket` (que los entrega a los navegadores). Ninguno de los
dos conoce al otro: se comunican solo a través de Redis.
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from src.shared.application.ports.event_publisher import EventPublisherPort
from src.shared.domain.events import (
    AttemptGraded,
    DomainEvent,
    MaterialProcessed,
    MaterialStatusChanged,
    UserEnrolled,
)
from src.shared.infrastructure.logging import get_logger

logger = get_logger("events")


class RedisChannelPublisher(EventPublisherPort):
    """Traduce eventos de dominio a mensajes de grupo del channel layer."""

    #: evento → función que calcula (grupo, tipo de mensaje)
    ROUTES: dict[type[DomainEvent], str] = {
        MaterialStatusChanged: "material",
        MaterialProcessed: "material",
        AttemptGraded: "user",
        UserEnrolled: "user",
    }

    def __init__(self) -> None:
        self._layer = get_channel_layer()

    def publish(self, event: DomainEvent) -> None:
        group = self._group_for(event)
        if group is None:
            logger.debug("Evento sin ruta de tiempo real", extra={"event": event.name})
            return
        self.send_to_group(
            group,
            {"type": "domain.event", "event": event.name, **event.payload()},
        )

    def publish_many(self, events: list[DomainEvent]) -> None:
        for event in events:
            self.publish(event)

    def send_to_group(self, group: str, message: dict[str, Any]) -> None:
        if self._layer is None:  # pragma: no cover - sin channel layer configurado
            logger.warning("Channel layer no disponible; evento descartado")
            return
        try:
            async_to_sync(self._layer.group_send)(group, message)
        except Exception:  # pragma: no cover - el tiempo real nunca rompe el flujo
            logger.exception("Fallo al publicar en el channel layer", extra={"group": group})

    # ── Interno ──────────────────────────────────────────────
    def _group_for(self, event: DomainEvent) -> str | None:
        kind = self.ROUTES.get(type(event))
        if kind == "material":
            return f"material.{getattr(event, 'material_id')}"
        if kind == "user":
            return f"user.{getattr(event, 'user_id')}"
        return None


class NullEventPublisher(EventPublisherPort):
    """Doble para tests y comandos sin infraestructura de tiempo real."""

    def __init__(self) -> None:
        self.published: list[DomainEvent] = []
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def publish(self, event: DomainEvent) -> None:
        self.published.append(event)

    def publish_many(self, events: list[DomainEvent]) -> None:
        self.published.extend(events)

    def send_to_group(self, group: str, message: dict[str, Any]) -> None:
        self.messages.append((group, message))
