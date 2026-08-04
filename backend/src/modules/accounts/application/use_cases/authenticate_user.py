"""CU-01 · Autenticarse."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import authenticate

from src.shared.application.use_case import UseCase
from src.shared.domain.exceptions import DomainError, PermissionDeniedError
from src.shared.domain.value_object import Email

from ...infrastructure.models import AuditLog, User


class AuthenticationFailed(DomainError):
    code = "AUTHENTICATION_FAILED"
    default_message = "Correo o contraseña incorrectos."


class UserDisabled(PermissionDeniedError):
    code = "USER_DISABLED"
    default_message = "Su cuenta está desactivada. Contacte al administrador."


class TenantSuspended(PermissionDeniedError):
    code = "TENANT_SUSPENDED"
    default_message = "La empresa se encuentra suspendida."


@dataclass(frozen=True)
class AuthenticateInput:
    email: str
    password: str
    ip_address: str | None = None
    user_agent: str = ""


@dataclass(frozen=True)
class AuthenticateOutput:
    user: User


class AuthenticateUserUseCase(UseCase[AuthenticateInput, AuthenticateOutput]):
    """
    Valida credenciales y las reglas de acceso, y deja rastro en auditoría.

    La emisión de los JWT es responsabilidad de la capa de presentación
    (SimpleJWT); aquí solo se decide SI el acceso es legítimo.
    """

    def execute(self, data: AuthenticateInput) -> AuthenticateOutput:
        email = Email(data.email)  # valida formato

        user = authenticate(username=str(email), password=data.password)

        if user is None:
            self._audit(None, AuditLog.Action.LOGIN_FAILED, data, {"email": str(email)})
            raise AuthenticationFailed

        if not user.is_active:
            self._audit(user, AuditLog.Action.LOGIN_FAILED, data, {"reason": "inactive"})
            raise UserDisabled

        if user.company_id and not user.company.is_active:
            self._audit(user, AuditLog.Action.LOGIN_FAILED, data, {"reason": "tenant"})
            raise TenantSuspended

        self._audit(user, AuditLog.Action.LOGIN_SUCCESS, data, {})
        return AuthenticateOutput(user=user)

    @staticmethod
    def _audit(user, action, data: AuthenticateInput, changes: dict) -> None:
        AuditLog.objects.create(
            company_id=getattr(user, "company_id", None),
            user=user,
            action=action,
            entity_type="User",
            entity_id=getattr(user, "id", None),
            ip_address=data.ip_address,
            user_agent=data.user_agent[:500],
            changes=changes,
        )
