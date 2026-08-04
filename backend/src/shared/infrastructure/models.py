"""Modelos base compartidos por todos los módulos."""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from .managers import AllObjectsManager, SoftDeleteManager


class UUIDModel(models.Model):
    """Clave primaria UUID v4 (evita enumeración y facilita la fusión de datos)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard: bool = False):  # type: ignore[override]
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])
        return (1, {self._meta.label: 1})

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class BaseModel(UUIDModel, TimeStampedModel):
    """Base habitual: UUID + timestamps."""

    class Meta:
        abstract = True


class BaseSoftDeleteModel(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """Base con borrado lógico."""

    class Meta:
        abstract = True
