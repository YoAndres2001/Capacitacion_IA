"""Managers y QuerySets base (borrado lógico + aislamiento por empresa)."""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from .tenancy import get_current_company, tenant_filtering_disabled


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self) -> SoftDeleteQuerySet:
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> SoftDeleteQuerySet:
        return self.filter(deleted_at__isnull=False)

    def delete(self):  # type: ignore[override]
        """Borrado lógico masivo."""
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):  # type: ignore[misc]
    """Manager por defecto: oculta los registros borrados lógicamente."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):  # type: ignore[misc]
    """Manager que incluye los registros borrados (auditoría y administración)."""


class TenantQuerySet(SoftDeleteQuerySet):
    def for_company(self, company_id) -> TenantQuerySet:
        return self.filter(company_id=company_id)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """
    Filtra automáticamente por la empresa del contexto (RN-01).

    Si no hay empresa en contexto (tarea Celery, shell, comando), no filtra:
    en esos escenarios el filtrado es responsabilidad explícita del llamador,
    que debería usar `company_scope(...)`.
    """

    def get_queryset(self) -> TenantQuerySet:
        qs = super().get_queryset().filter(deleted_at__isnull=True)
        if tenant_filtering_disabled():
            return qs
        company_id = get_current_company()
        if company_id is not None:
            qs = qs.filter(company_id=company_id)
        return qs
