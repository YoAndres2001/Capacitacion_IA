"""Implementación de `NotifierPort`: correo SMTP + avisos in-app por WebSocket."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from src.shared.application.ports.notifier import NotifierPort
from src.shared.infrastructure.events.publisher import RedisChannelPublisher
from src.shared.infrastructure.logging import get_logger

logger = get_logger("notifier")


class EmailNotifier(NotifierPort):
    def __init__(self, publisher: RedisChannelPublisher | None = None) -> None:
        self._publisher = publisher or RedisChannelPublisher()

    def send_email(
        self,
        *,
        to: list[str],
        subject: str,
        template: str,
        context: dict[str, Any],
    ) -> None:
        ctx = {"frontend_url": settings.FRONTEND_URL, **context}
        try:
            html = render_to_string(f"emails/{template}.html", ctx)
            text = render_to_string(f"emails/{template}.txt", ctx)
        except Exception:  # pragma: no cover - plantilla ausente
            logger.exception("Plantilla de correo no encontrada", extra={"template": template})
            return

        message = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=to,
        )
        message.attach_alternative(html, "text/html")
        try:
            message.send(fail_silently=False)
        except Exception:  # pragma: no cover - SMTP caído no debe romper el caso de uso
            logger.exception("No se pudo enviar el correo", extra={"template": template})

    def notify_user(self, user_id: str, payload: dict[str, Any]) -> None:
        self._publisher.send_to_group(
            f"user.{user_id}", {"type": "notification.message", **payload}
        )
