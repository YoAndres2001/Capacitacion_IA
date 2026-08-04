"""Middlewares transversales: identificador de petición y contexto de tenant."""

from __future__ import annotations

import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

from src.shared.infrastructure.logging import (
    company_id_var,
    request_id_var,
    user_id_var,
)
from src.shared.infrastructure.tenancy import set_current_company


class RequestIDMiddleware:
    """Asigna un `request_id` a cada petición y lo propaga a logs y respuesta."""

    HEADER = "HTTP_X_REQUEST_ID"

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.META.get(self.HEADER) or uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response["X-Request-ID"] = request_id
        return response


class TenantMiddleware:
    """
    Resuelve la empresa del usuario autenticado y la deja en el contexto (RN-01).

    A partir de aquí, los managers que heredan de `TenantManager` filtran solos.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        company_id = None
        user = getattr(request, "user", None)

        # DRF autentica en la vista, no en el middleware: se resuelve el JWT aquí
        # para que el contexto esté disponible desde el primer queryset.
        if user is None or not getattr(user, "is_authenticated", False):
            user = self._user_from_jwt(request)

        if user is not None and getattr(user, "is_authenticated", False):
            company_id = getattr(user, "company_id", None)
            user_id_var.set(str(user.pk))

        set_current_company(company_id)
        company_id_var.set(str(company_id) if company_id else "")

        try:
            return self.get_response(request)
        finally:
            set_current_company(None)

    @staticmethod
    def _user_from_jwt(request: HttpRequest):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith("Bearer "):
            return None
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication

            result = JWTAuthentication().authenticate(request)  # type: ignore[arg-type]
        except Exception:
            return None
        return result[0] if result else None
