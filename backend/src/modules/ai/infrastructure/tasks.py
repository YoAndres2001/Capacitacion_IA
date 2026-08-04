"""Tareas Celery del módulo IA."""

from __future__ import annotations

from celery import shared_task

from src.shared.container import (
    get_document_extractor,
    get_embeddings,
    get_event_publisher,
    get_llm,
    get_storage,
    get_transcriber,
    get_vector_store,
)
from src.shared.domain.exceptions import ExternalServiceError, NotFoundError
from src.shared.infrastructure.logging import get_logger

from ..application.use_cases.ingest_material import IngestInput, IngestMaterialUseCase

logger = get_logger("ai.tasks")


def _build_ingest_use_case() -> IngestMaterialUseCase:
    return IngestMaterialUseCase(
        storage=get_storage(),
        transcriber=get_transcriber(),
        embeddings=get_embeddings(),
        llm=get_llm(),
        publisher=get_event_publisher(),
        vector_store_factory=get_vector_store,
        extractor_factory=get_document_extractor,
    )


@shared_task(
    name="ai.ingest_material",
    bind=True,
    queue="ingest",
    autoretry_for=(ExternalServiceError,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
    acks_late=True,
)
def ingest_material(self, material_id: str, force: bool = False) -> dict:
    """CU-08 · Procesa un material de principio a fin."""
    logger.info(f"Inicio de ingesta del material {material_id} (tarea {self.request.id})")

    try:
        result = _build_ingest_use_case().execute(
            # El id de la tarea se guarda en ProcessingJob para poder revocarla
            # si el usuario elimina el material mientras se procesa.
            IngestInput(material_id=material_id, force=force, task_id=self.request.id or "")
        )
    except NotFoundError:
        # El material se eliminó antes de que el worker tomara la tarea. Es
        # normal (borrado mientras estaba en cola), no un fallo que reportar
        # con traza: se cierra la tarea en silencio.
        logger.info(f"Ingesta omitida: el material {material_id} ya no existe")
        return {"material_id": material_id, "skipped": "deleted"}

    return {
        "material_id": str(result.material_id),
        "chunks": result.chunk_count,
        "partial": result.partial,
    }


@shared_task(name="ai.rebuild_project_index", bind=True, queue="ai", max_retries=2)
def rebuild_project_index(self, project_id: str) -> dict:
    """
    CU-18 · Reconstruye el índice FAISS del proyecto desde PostgreSQL.

    Los `chunks` son la fuente de verdad (RN-10): esta tarea regenera los
    embeddings con el proveedor configurado y hace un intercambio atómico del
    índice, sin cortar el servicio de chat.
    """
    from django.conf import settings
    from django.utils import timezone

    from src.modules.projects.infrastructure.models import VectorCollection

    from ..application.ports.vector_store import VectorRecord
    from .models import Chunk

    collection, _ = VectorCollection.objects.get_or_create(
        project_id=project_id, defaults={"index_path": str(project_id)}
    )
    collection.status = VectorCollection.Status.REBUILDING
    collection.save(update_fields=["status", "updated_at"])

    embeddings = get_embeddings()
    store = get_vector_store(project_id)
    batch_size = settings.RAG_SETTINGS["EMBED_BATCH_SIZE"]

    try:
        chunks = list(
            Chunk.objects.filter(project_id=project_id)
            .order_by("material_id", "index")
            .only("id", "content", "material_id", "training_id", "project_id",
                  "index", "start_time", "end_time", "page", "heading")
        )

        records: list[VectorRecord] = []
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = embeddings.embed_documents([chunk.content for chunk in batch])
            records.extend(
                VectorRecord(chunk_id=chunk.id, vector=vector, metadata=chunk.as_metadata())
                for chunk, vector in zip(batch, vectors)
            )
            logger.info(
                "Embeddings regenerados",
                extra={"project_id": project_id, "done": len(records), "total": len(chunks)},
            )

        store.rebuild(records)

        Chunk.objects.filter(project_id=project_id).update(
            embedded=True, embedding_model=embeddings.model_name
        )

        collection.last_rebuilt_at = timezone.now()
        collection.index_type = store.stats().get("index_type", "")
        collection.save(update_fields=["last_rebuilt_at", "index_type", "updated_at"])
        collection.mark_ready(
            count=len(records),
            dimension=embeddings.dimension,
            model=embeddings.model_name,
            provider=embeddings.provider_name,
        )

        get_event_publisher().send_to_group(
            f"project.{project_id}",
            {"type": "index.rebuilt", "project_id": str(project_id), "vectors": len(records)},
        )
        return {"project_id": str(project_id), "vectors": len(records)}

    except Exception as exc:
        collection.status = VectorCollection.Status.ERROR
        collection.error_detail = str(exc)[:2000]
        collection.save(update_fields=["status", "error_detail", "updated_at"])
        logger.exception("Fallo la reconstrucción del índice")
        raise


@shared_task(name="ai.cleanup_expired_uploads", queue="default")
def cleanup_expired_uploads() -> dict:
    """Tarea programada: limpia sesiones de carga vencidas y sus trozos."""
    import shutil
    from pathlib import Path

    from django.conf import settings
    from django.utils import timezone

    from src.modules.trainings.infrastructure.models import UploadSession

    expired = UploadSession.objects.filter(expires_at__lt=timezone.now(), completed=False)
    removed = 0
    base = Path(settings.STORAGE_SETTINGS["TMP_DIR"]) / "uploads"

    for session in expired:
        shutil.rmtree(base / str(session.id), ignore_errors=True)
        removed += 1

    expired.delete()
    return {"removed": removed}


@shared_task(name="ai.health_check_provider", queue="ai")
def health_check_provider() -> dict:
    """Comprueba periódicamente que el proveedor de IA responde."""
    llm = get_llm()
    available = llm.is_available()
    if not available:
        logger.error("Proveedor de IA no disponible", extra={"provider": llm.provider_name})
    return {"provider": llm.provider_name, "model": llm.model_name, "available": available}
