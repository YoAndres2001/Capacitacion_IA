"""Puerto de publicación de eventos (tiempo real y efectos secundarios)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.shared.domain.events import DomainEvent


class EventPublisherPort(ABC):
    """
    Publica eventos de dominio hacia el exterior.

    La implementación de infraestructura los traduce a `group_send` del channel
    layer de Redis (que consume el contenedor `websocket`) y/o a tareas Celery.
    """

    @abstractmethod
    def publish(self, event: DomainEvent) -> None: ...

    @abstractmethod
    def publish_many(self, events: list[DomainEvent]) -> None: ...

    @abstractmethod
    def send_to_group(self, group: str, message: dict[str, Any]) -> None:
        """Envío directo a un grupo del channel layer (streaming de tokens, progreso)."""
