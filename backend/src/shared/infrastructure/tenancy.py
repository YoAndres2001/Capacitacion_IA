"""
Contexto de tenant (multi-empresa).

El middleware resuelve la empresa desde el JWT y la deja en un `ContextVar`;
los managers de modelos con tenant filtran automáticamente por ella (RN-01).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator
from uuid import UUID

_current_company: ContextVar[UUID | None] = ContextVar("current_company_id", default=None)
_bypass: ContextVar[bool] = ContextVar("tenant_bypass", default=False)


def set_current_company(company_id: UUID | None) -> None:
    _current_company.set(company_id)


def get_current_company() -> UUID | None:
    return _current_company.get()


def tenant_filtering_disabled() -> bool:
    return _bypass.get()


@contextmanager
def company_scope(company_id: UUID | None) -> Iterator[None]:
    """Ejecuta un bloque en el contexto de una empresa (útil en tareas Celery)."""
    token = _current_company.set(company_id)
    try:
        yield
    finally:
        _current_company.reset(token)


@contextmanager
def bypass_tenant() -> Iterator[None]:
    """
    Desactiva el filtro por empresa dentro del bloque.

    Uso legítimo: comandos de administración, migraciones de datos y tareas
    de mantenimiento que operan sobre todos los tenants. NUNCA en una vista.
    """
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)
