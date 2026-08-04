"""
Jerarquía de excepciones del dominio.

Estas excepciones son PURAS: no conocen HTTP ni Django. La capa de presentación
las traduce a códigos HTTP en `shared/presentation/exception_handler.py`.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Raíz de todos los errores de negocio."""

    code: str = "DOMAIN_ERROR"
    default_message: str = "Se produjo un error de dominio."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code:
            self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class ValidationError(DomainError):
    code = "VALIDATION_ERROR"
    default_message = "Los datos proporcionados no son válidos."


class InvalidStateTransition(DomainError):
    code = "INVALID_STATE_TRANSITION"
    default_message = "La transición de estado solicitada no está permitida."

    def __init__(self, entity: str, current: str, target: str) -> None:
        super().__init__(
            f"{entity} no puede pasar de '{current}' a '{target}'.",
            details={"entity": entity, "current": current, "target": target},
        )


class BusinessRuleViolation(DomainError):
    code = "BUSINESS_RULE_VIOLATION"
    default_message = "La operación viola una regla de negocio."


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    default_message = "El recurso solicitado no existe."


class PermissionDeniedError(DomainError):
    code = "PERMISSION_DENIED"
    default_message = "No tiene permisos para realizar esta acción."


class ConflictError(DomainError):
    code = "CONFLICT"
    default_message = "El recurso ya existe o está en conflicto."


class ExternalServiceError(DomainError):
    code = "EXTERNAL_SERVICE_ERROR"
    default_message = "Un servicio externo no está disponible."


# ── Reglas de negocio concretas ──────────────────────────────


class TrainingNotPublishable(BusinessRuleViolation):
    code = "TRAINING_NOT_PUBLISHABLE"
    default_message = (
        "La capacitación no puede publicarse: necesita al menos una lección "
        "con material disponible."
    )


class ExamNotPublishable(BusinessRuleViolation):
    code = "EXAM_NOT_PUBLISHABLE"
    default_message = "El examen no puede publicarse: revise preguntas y puntajes."


class ExamLocked(BusinessRuleViolation):
    code = "EXAM_LOCKED"
    default_message = "El examen ya tiene intentos registrados y no puede modificarse."


class MaxAttemptsReached(BusinessRuleViolation):
    code = "MAX_ATTEMPTS_REACHED"
    default_message = "Alcanzó el número máximo de intentos permitidos."


class InsufficientProgress(BusinessRuleViolation):
    code = "INSUFFICIENT_PROGRESS"
    default_message = "Debe completar más contenido antes de rendir la evaluación."


class MaterialNotQueryable(BusinessRuleViolation):
    code = "MATERIAL_NOT_READY"
    default_message = "El material aún no está disponible para consultas."


class NotEnrolled(PermissionDeniedError):
    code = "NOT_ENROLLED"
    default_message = "No está inscrito en esta capacitación."


class InsufficientContent(BusinessRuleViolation):
    code = "INSUFFICIENT_CONTENT"
    default_message = "No hay contenido suficiente para generar la evaluación."


class AIProviderUnavailable(ExternalServiceError):
    code = "AI_PROVIDER_UNAVAILABLE"
    default_message = "El proveedor de IA no está disponible en este momento."


class InvalidFileType(ValidationError):
    code = "INVALID_FILE_TYPE"
    default_message = "El tipo de archivo no está permitido."


class FileTooLarge(ValidationError):
    code = "FILE_TOO_LARGE"
    default_message = "El archivo supera el tamaño máximo permitido."


class DuplicateMaterial(ConflictError):
    code = "DUPLICATE_MATERIAL"
    default_message = "Este archivo ya fue cargado en el proyecto."
