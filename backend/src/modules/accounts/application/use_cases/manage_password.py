"""RF-007 · Recuperación y cambio de contraseña."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from src.shared.application.ports.notifier import NotifierPort
from src.shared.application.use_case import UseCase
from src.shared.domain.exceptions import ValidationError
from src.shared.domain.value_object import Email

from ...infrastructure.models import AuditLog, PasswordResetToken, User

TOKEN_TTL = timedelta(hours=1)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class RequestResetInput:
    email: str
    ip_address: str | None = None


class RequestPasswordResetUseCase(UseCase[RequestResetInput, None]):
    """
    Genera un token de un solo uso y envía el enlace.

    Nunca revela si el correo existe: siempre responde igual (evita enumeración
    de usuarios).
    """

    def __init__(self, notifier: NotifierPort) -> None:
        self._notifier = notifier

    def execute(self, data: RequestResetInput) -> None:
        try:
            email = Email(data.email)
        except ValidationError:
            return  # respuesta indistinguible

        user = User.objects.filter(email=str(email), is_active=True).first()
        if user is None:
            return

        raw_token = secrets.token_urlsafe(48)
        PasswordResetToken.objects.create(
            user=user,
            token_hash=_hash(raw_token),
            expires_at=timezone.now() + TOKEN_TTL,
            requested_ip=data.ip_address,
        )

        self._notifier.send_email(
            to=[user.email],
            subject="Recuperación de contraseña · Capacita IA",
            template="password_reset",
            context={
                "user_name": user.get_short_name(),
                "reset_token": raw_token,
                "expires_hours": int(TOKEN_TTL.total_seconds() // 3600),
            },
        )

        AuditLog.objects.create(
            company_id=user.company_id,
            user=user,
            action=AuditLog.Action.PASSWORD_RESET_REQUESTED,
            entity_type="User",
            entity_id=user.id,
            ip_address=data.ip_address,
        )


@dataclass(frozen=True)
class ConfirmResetInput:
    token: str
    new_password: str


class InvalidResetToken(ValidationError):
    code = "INVALID_RESET_TOKEN"
    default_message = "El enlace de recuperación es inválido o ya fue utilizado."


class ConfirmPasswordResetUseCase(UseCase[ConfirmResetInput, None]):
    def execute(self, data: ConfirmResetInput) -> None:
        record = PasswordResetToken.objects.filter(token_hash=_hash(data.token)).first()
        if record is None or not record.is_valid:
            raise InvalidResetToken

        user = record.user
        _validate_password(data.new_password, user)

        user.set_password(data.new_password)
        user.save(update_fields=["password"])
        record.consume()

        # Invalida el resto de tokens vigentes del usuario.
        PasswordResetToken.objects.filter(user=user, used_at__isnull=True).update(
            used_at=timezone.now()
        )

        AuditLog.objects.create(
            company_id=user.company_id,
            user=user,
            action=AuditLog.Action.PASSWORD_CHANGED,
            entity_type="User",
            entity_id=user.id,
            changes={"method": "reset"},
        )


@dataclass(frozen=True)
class ChangePasswordInput:
    user: User
    current_password: str
    new_password: str


class ChangePasswordUseCase(UseCase[ChangePasswordInput, None]):
    def execute(self, data: ChangePasswordInput) -> None:
        if not data.user.check_password(data.current_password):
            raise ValidationError("La contraseña actual no es correcta.")

        _validate_password(data.new_password, data.user)
        data.user.set_password(data.new_password)
        data.user.save(update_fields=["password"])

        AuditLog.objects.create(
            company_id=data.user.company_id,
            user=data.user,
            action=AuditLog.Action.PASSWORD_CHANGED,
            entity_type="User",
            entity_id=data.user.id,
            changes={"method": "self-service"},
        )


def _validate_password(password: str, user: User) -> None:
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise ValidationError("; ".join(exc.messages)) from exc
