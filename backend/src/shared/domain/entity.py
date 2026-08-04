"""Bloques base para entidades y agregados del dominio."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from .events import DomainEvent


@dataclass(kw_only=True)
class Entity:
    """Entidad con identidad. La igualdad se define por el `id`, no por el valor."""

    id: UUID = field(default_factory=uuid4)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return type(self) is type(other) and self.id == other.id

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.id))


@dataclass(kw_only=True)
class AggregateRoot(Entity):
    """
    Raíz de agregado: única puerta de entrada a su consistencia interna
    y punto de registro de eventos de dominio.
    """

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None
    _events: list[DomainEvent] = field(default_factory=list, repr=False, compare=False)

    def record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Devuelve y limpia los eventos acumulados (los publica la capa de aplicación)."""
        events, self._events = self._events, []
        return events

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self.__dict__.items()
            if not key.startswith("_")
        }
