"""
Traducción de excepciones de dominio a respuestas HTTP.

Es el único punto donde el dominio se acopla al protocolo, y lo hace en una
sola dirección: dominio → HTTP.
"""

from __future__ import annotations

from typing import Any

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from src.shared.domain.exceptions import (
    BusinessRuleViolation,
    ConflictError,
    DomainError,
    ExternalServiceError,
    InvalidStateTransition,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.shared.infrastructure.logging import get_logger, request_id_var

logger = get_logger("http")

STATUS_MAP: list[tuple[type[DomainError], int]] = [
    (ValidationError, status.HTTP_400_BAD_REQUEST),
    (PermissionDeniedError, status.HTTP_403_FORBIDDEN),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (InvalidStateTransition, status.HTTP_409_CONFLICT),
    (ExternalServiceError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (BusinessRuleViolation, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (DomainError, status.HTTP_400_BAD_REQUEST),
]


def _status_for(exc: DomainError) -> int:
    for exc_type, http_status in STATUS_MAP:
        if isinstance(exc, exc_type):
            return http_status
    return status.HTTP_400_BAD_REQUEST


def _envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id_var.get(),
        }
    }


def domain_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Handler de DRF: uniforma TODAS las respuestas de error (ver docs/10-api-rest.md §1)."""

    if isinstance(exc, DomainError):
        http_status = _status_for(exc)
        if http_status >= 500:
            logger.error("Error de dominio", extra={"code": exc.code, "message": exc.message})
        return Response(_envelope(exc.code, exc.message, exc.details), status=http_status)

    if isinstance(exc, Http404):
        return Response(
            _envelope("NOT_FOUND", "El recurso solicitado no existe."),
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, DRFValidationError):
        return Response(
            _envelope("VALIDATION_ERROR", "Los datos enviados no son válidos.", exc.detail),
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, PermissionDenied):
        return Response(
            _envelope("PERMISSION_DENIED", str(exc.detail)),
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, APIException):
        response = drf_exception_handler(exc, context)
        if response is not None:
            code = getattr(exc, "default_code", "API_ERROR")
            response.data = _envelope(str(code).upper(), str(exc.detail), None)["error"]
            response.data = {"error": response.data}
            return response

    # Excepción no controlada: se registra y se devuelve un 500 sin filtrar detalles.
    logger.exception("Excepción no controlada")
    return drf_exception_handler(exc, context)
