"""CU-07 · Registro de un material subido y disparo del pipeline de ingesta."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from django.db import transaction

from src.shared.application.ports.event_publisher import EventPublisherPort
from src.shared.application.ports.storage import StoragePort
from src.shared.application.use_case import UseCase
from src.shared.domain.events import MaterialUploaded
from src.shared.domain.exceptions import DuplicateMaterial, NotFoundError

from ...infrastructure.models import Lesson, Material
from ...infrastructure.validators import (
    material_type_for,
    sanitize_filename,
    sha256_of,
    validate_real_content,
)


@dataclass(frozen=True)
class UploadMaterialInput:
    lesson_id: UUID
    temp_path: Path
    original_filename: str
    user_id: UUID


@dataclass(frozen=True)
class UploadMaterialOutput:
    material: Material


class UploadMaterialUseCase(UseCase[UploadMaterialInput, UploadMaterialOutput]):
    """
    Valida el archivo ya ensamblado, lo mueve al almacenamiento definitivo,
    crea el `Material` en PENDING y encola la ingesta.
    """

    def __init__(self, storage: StoragePort, publisher: EventPublisherPort) -> None:
        self._storage = storage
        self._publisher = publisher

    @transaction.atomic
    def execute(self, data: UploadMaterialInput) -> UploadMaterialOutput:
        lesson = (
            Lesson.objects.select_related("module__training__project__company")
            .filter(id=data.lesson_id)
            .first()
        )
        if lesson is None:
            raise NotFoundError("La lección indicada no existe.")

        project = lesson.module.training.project
        filename = sanitize_filename(data.original_filename)
        material_type = material_type_for(filename)

        # El MIME real manda sobre la extensión declarada por el cliente.
        mime_type = validate_real_content(data.temp_path, material_type)
        checksum = sha256_of(data.temp_path)

        existing = Material.objects.filter(project=project, sha256=checksum).first()
        if existing is not None:
            raise DuplicateMaterial(
                "Este archivo ya fue cargado en el proyecto.",
                details={"material_id": str(existing.id), "lesson_id": str(existing.lesson_id)},
            )

        material = Material.objects.create(
            lesson=lesson,
            project=project,
            original_filename=filename,
            file="",  # se completa tras mover el archivo
            mime_type=mime_type,
            size_bytes=data.temp_path.stat().st_size,
            sha256=checksum,
            type=material_type,
            uploaded_by_id=data.user_id,
        )

        company_slug = project.company.slug
        relative = f"{company_slug}/{project.id}/{material.id}/{filename}"
        with data.temp_path.open("rb") as handle:
            self._storage.save(relative, handle)

        material.file = relative
        material.save(update_fields=["file", "updated_at"])

        data.temp_path.unlink(missing_ok=True)

        transaction.on_commit(lambda: self._enqueue(material))

        return UploadMaterialOutput(material=material)

    def _enqueue(self, material: Material) -> None:
        from src.modules.ai.infrastructure.tasks import ingest_material

        self._publisher.publish(
            MaterialUploaded(
                material_id=material.id,
                lesson_id=material.lesson_id,
                project_id=material.project_id,
                material_type=material.type,
            )
        )
        ingest_material.delay(str(material.id))
