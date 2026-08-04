"""Puerto de notificaciones (correo y avisos in-app)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class NotifierPort(ABC):
    @abstractmethod
    def send_email(
        self,
        *,
        to: list[str],
        subject: str,
        template: str,
        context: dict[str, Any],
    ) -> None: ...

    @abstractmethod
    def notify_user(self, user_id: str, payload: dict[str, Any]) -> None:
        """Notificación in-app entregada por WebSocket."""
