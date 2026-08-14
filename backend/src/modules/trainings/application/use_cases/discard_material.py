"""
Retirada de material de circulación.

Es el paso obligatorio antes de borrar cualquier contenedor de material
(capacitación, módulo o lección): el borrado lógico de Django no cascadea, así
que sin esto los materiales seguirían activos aunque su curso ya no exista. Las
consecuencias son visibles para el usuario: su `sha256` sigue ocupando el hueco
del proyecto —y rechaza volver a subir el mismo archivo— y sus fragmentos
siguen respondiendo en el chat.
"""

from __future__ import annotations

from contextlib import suppress

from ...infrastructure.models import Material, ProcessingJob


def cancel_running_ingestion(material) -> None:
    """
    Revoca la tarea de ingesta en curso.

    Un worker puede estar transcribiendo un video de una hora: dejarlo
    correr tras el borrado desperdicia el slot y retrasa las subidas
    siguientes. La tarea además comprueba por su cuenta si el material
    desapareció, así que la revocación es la vía rápida, no la única.
    """
    from config.celery import app as celery_app

    running = material.processing_jobs.filter(status=ProcessingJob.Status.RUNNING).exclude(
        celery_task_id=""
    )

    for job in running:
        # El broker puede no responder; la tarea igual se autocomprueba.
        with suppress(Exception):
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
        job.finish(success=False, error="Cancelada: el material fue eliminado.")


def discard_materials(materials) -> int:
    """
    Cancela la ingesta de los materiales, borra sus fragmentos, marca la
    colección vectorial de su proyecto para reconstruirse y los borra
    lógicamente. Devuelve cuántos se retiraron.
    """
    from src.modules.ai.infrastructure.models import Chunk
    from src.modules.projects.infrastructure.models import VectorCollection

    pending = list(materials)
    if not pending:
        return 0

    for material in pending:
        cancel_running_ingestion(material)

    ids = [material.id for material in pending]
    Chunk.objects.filter(material_id__in=ids).delete()
    VectorCollection.objects.filter(
        project_id__in={material.project_id for material in pending}
    ).update(status=VectorCollection.Status.PENDING)
    # `delete()` sobre el queryset con borrado lógico es un UPDATE masivo.
    Material.objects.filter(id__in=ids).delete()
    return len(ids)
