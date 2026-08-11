"""
CU-08 · Pipeline de ingesta de un material.

Orquesta las etapas descritas en docs/13-flujo-procesamiento.md:
extracción → normalización → chunking → embeddings → índice → análisis LLM.

Todas las dependencias externas entran por puertos (transcriptor, extractor,
embeddings, almacén vectorial, LLM, storage, publicador de eventos), de modo
que el pipeline es probable con dobles y no depende de ningún proveedor.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.db import transaction

from src.shared.application.ports.event_publisher import EventPublisherPort
from src.shared.application.ports.storage import StoragePort
from src.shared.application.use_case import UseCase
from src.shared.domain.events import MaterialProcessed
from src.shared.domain.exceptions import DomainError, NotFoundError
from src.shared.infrastructure.logging import get_logger

from ...domain.chunking import ChunkingPolicy, SourceBlock
from ..ports.embeddings import EmbeddingsPort
from ..ports.llm import LLMPort
from ..ports.transcriber import TranscriberPort
from ..ports.vector_store import VectorRecord, VectorStorePort

logger = get_logger("ai.ingest")


class MaterialDeleted(DomainError):
    """El material se eliminó mientras se procesaba: la ingesta se aborta."""

    code = "MATERIAL_DELETED"
    default_message = "El material fue eliminado durante su procesamiento."


@dataclass(frozen=True)
class IngestInput:
    material_id: UUID
    force: bool = False
    task_id: str = ""


@dataclass
class IngestOutput:
    material_id: UUID
    chunk_count: int
    partial: bool = False


class IngestMaterialUseCase(UseCase[IngestInput, IngestOutput]):
    def __init__(
        self,
        *,
        storage: StoragePort,
        transcriber: TranscriberPort,
        embeddings: EmbeddingsPort,
        llm: LLMPort,
        publisher: EventPublisherPort,
        vector_store_factory,
        extractor_factory,
    ) -> None:
        self._storage = storage
        self._transcriber = transcriber
        self._embeddings = embeddings
        self._llm = llm
        self._publisher = publisher
        self._vector_store_factory = vector_store_factory
        self._extractor_factory = extractor_factory

    # ═════════════════════════════════════════════════════════
    def execute(self, data: IngestInput) -> IngestOutput:
        from src.modules.trainings.infrastructure.models import Material, ProcessingJob

        material = (
            Material.objects.select_related("project__company", "lesson__module__training")
            .filter(id=data.material_id)
            .first()
        )
        if material is None:
            raise NotFoundError("El material no existe.")

        job = ProcessingJob.objects.create(
            material=material, step="start", celery_task_id=data.task_id
        )

        if data.force:
            self._purge_previous_results(material)

        try:
            material.mark_processing()
            self._notify(material, step="extract", progress=5)

            blocks, extras = self._extract(material, job)
            self._abort_if_deleted(material)

            material.mark_analyzing()
            self._notify(material, step="chunking", progress=45)

            chunks = self._persist_chunks(material, blocks)
            self._notify(material, step="embeddings", progress=60)

            self._embed_and_index(material, chunks, job)
            self._abort_if_deleted(material)
            self._notify(material, step="analysis", progress=80)

            partial = self._analyze(material, blocks, extras)

            material.mark_available(partial=partial)
            job.finish(success=True)
            self._notify(material, step="done", progress=100)

            self._publisher.publish(
                MaterialProcessed(
                    material_id=material.id,
                    project_id=material.project_id,
                    chunk_count=len(chunks),
                    partial=partial,
                )
            )
            return IngestOutput(material_id=material.id, chunk_count=len(chunks), partial=partial)

        except MaterialDeleted:
            # No es un fallo: el usuario eliminó el material. Se libera el slot
            # del worker sin marcar error ni notificar a nadie.
            logger.info(f"Ingesta abortada: material {material.id} eliminado")
            job.finish(success=False, error="Material eliminado durante el procesamiento.")
            self._cleanup_orphan_results(material)
            return IngestOutput(material_id=material.id, chunk_count=0)

        except DomainError as exc:
            logger.warning(
                "Ingesta fallida",
                extra={"material_id": str(material.id), "code": exc.code},
            )
            material.mark_error(exc.code, exc.message)
            job.finish(success=False, error=exc.message)
            self._notify(material, step="error", progress=job.progress)
            raise
        except Exception as exc:  # pragma: no cover - salvaguarda
            logger.exception("Error inesperado en la ingesta")
            material.mark_error("INGESTION_FAILED", str(exc))
            job.finish(success=False, error=str(exc))
            self._notify(material, step="error", progress=job.progress)
            raise

    # ═════════════════════════════════════════════════════════
    #  Etapa 1 · Extracción
    # ═════════════════════════════════════════════════════════
    def _extract(self, material, job) -> tuple[list[SourceBlock], dict]:
        if material.is_video:
            return self._extract_from_video(material, job)
        return self._extract_from_document(material, job)

    def _extract_from_video(self, material, job) -> tuple[list[SourceBlock], dict]:
        from ...infrastructure.transcription import ffmpeg

        source = self._storage.absolute_path(material.file)
        work_dir = Path(settings.STORAGE_SETTINGS["TMP_DIR"]) / "ingest" / str(material.id)
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            info = ffmpeg.probe(source)
            if info.duration_seconds:
                material.duration_seconds = info.duration_seconds
                material.save(update_fields=["duration_seconds", "updated_at"])
                self._sync_lesson_duration(material, info.duration_seconds)

            if material.type == "VIDEO":
                thumbnail = ffmpeg.extract_thumbnail(source, work_dir / "thumb.jpg")
                if thumbnail:
                    relative = f"{material.project.company.slug}/{material.project_id}/{material.id}/thumb.jpg"
                    with thumbnail.open("rb") as handle:
                        self._storage.save(relative, handle)
                    material.thumbnail = relative
                    material.save(update_fields=["thumbnail", "updated_at"])

            # La extensión importa: ffmpeg deduce el contenedor de ella y el
            # códec es FLAC (ver `extract_audio`), no PCM.
            audio_path = ffmpeg.extract_audio(source, work_dir / "audio.flac")

            job.step = "transcription"
            job.save(update_fields=["step"])

            def report(percent: int) -> None:
                job.progress = min(40, 10 + int(percent * 0.3))
                job.save(update_fields=["progress"])
                self._notify(material, step="transcription", progress=job.progress)

            result = self._transcriber.transcribe(audio_path, on_progress=report)
            self._save_transcript(material, result)

            blocks = [
                SourceBlock(
                    text=segment.text,
                    order=segment.index,
                    start_time=segment.start,
                    end_time=segment.end,
                )
                for segment in result.segments
            ]
            return blocks, {"is_video": True, "language": result.language}

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _extract_from_document(self, material, job) -> tuple[list[SourceBlock], dict]:
        job.step = "extraction"
        job.save(update_fields=["step"])

        extractor = self._extractor_factory(material.type)
        result = extractor.extract(self._storage.absolute_path(material.file))

        if result.page_count:
            material.page_count = result.page_count
            material.save(update_fields=["page_count", "updated_at"])

        blocks = [
            SourceBlock(
                text=block.text,
                order=block.order,
                page=block.page,
                heading=block.heading,
            )
            for block in result.blocks
        ]
        return blocks, {"is_video": False, "language": result.language or "es"}

    def _save_transcript(self, material, result) -> None:
        from ...infrastructure.models import Transcript, TranscriptSegment

        with transaction.atomic():
            Transcript.objects.filter(material=material).delete()
            transcript = Transcript.objects.create(
                material=material,
                language=result.language,
                full_text=result.full_text,
                model=result.model,
                confidence=result.confidence,
            )
            TranscriptSegment.objects.bulk_create(
                [
                    TranscriptSegment(
                        transcript=transcript,
                        index=segment.index,
                        start_time=segment.start,
                        end_time=segment.end,
                        text=segment.text,
                    )
                    for segment in result.segments
                ],
                batch_size=500,
            )

        material.language = result.language
        material.save(update_fields=["language", "updated_at"])

    @staticmethod
    def _sync_lesson_duration(material, duration: int) -> None:
        """La duración de la lección determina el 90 % que marca la finalización."""
        lesson = material.lesson
        if lesson.duration_seconds < duration:
            lesson.duration_seconds = duration
            lesson.save(update_fields=["duration_seconds", "updated_at"])

    # ═════════════════════════════════════════════════════════
    #  Etapa 3 · Chunking
    # ═════════════════════════════════════════════════════════
    def _persist_chunks(self, material, blocks: list[SourceBlock]) -> list:
        from ...infrastructure.models import Chunk

        policy = ChunkingPolicy(
            chunk_size_tokens=settings.RAG_SETTINGS["CHUNK_SIZE_TOKENS"],
            overlap_tokens=settings.RAG_SETTINGS["CHUNK_OVERLAP_TOKENS"],
        )
        pieces = policy.split(blocks)

        training_id = material.lesson.module.training_id

        with transaction.atomic():
            Chunk.objects.filter(material=material).delete()
            created = Chunk.objects.bulk_create(
                [
                    Chunk(
                        material=material,
                        project_id=material.project_id,
                        training_id=training_id,
                        index=piece.index,
                        content=piece.content,
                        token_count=piece.token_count,
                        start_time=piece.start_time,
                        end_time=piece.end_time,
                        page=piece.page,
                        heading=(piece.heading or "")[:250],
                    )
                    for piece in pieces
                ],
                batch_size=200,
            )
        self._refresh_search_vectors(material)
        return created

    @staticmethod
    def _refresh_search_vectors(material) -> None:
        """Alimenta el componente full-text de la búsqueda híbrida."""
        from django.contrib.postgres.search import SearchVector

        from ...infrastructure.models import Chunk

        try:
            Chunk.objects.filter(material=material).update(
                search_vector=SearchVector("content", config="spanish")
            )
        except Exception:  # pragma: no cover - motor sin soporte
            logger.warning("No se pudo actualizar el search_vector")

    # ═════════════════════════════════════════════════════════
    #  Etapa 4 · Embeddings e indexación
    # ═════════════════════════════════════════════════════════
    def _embed_and_index(self, material, chunks: list, job) -> None:
        from ...infrastructure.models import Chunk

        if not chunks:
            return

        job.step = "embeddings"
        job.save(update_fields=["step"])

        store: VectorStorePort = self._vector_store_factory(material.project_id)
        store.delete_by_material(material.id)

        batch_size = settings.RAG_SETTINGS["EMBED_BATCH_SIZE"]
        model_name = self._embeddings.model_name
        total = len(chunks)

        for start in range(0, total, batch_size):
            batch = chunks[start : start + batch_size]
            vectors = self._embeddings.embed_documents([chunk.content for chunk in batch])

            store.add(
                [
                    VectorRecord(
                        chunk_id=chunk.id,
                        vector=vector,
                        metadata=chunk.as_metadata(),
                    )
                    for chunk, vector in zip(batch, vectors)
                ]
            )

            Chunk.objects.filter(id__in=[c.id for c in batch]).update(
                embedded=True, embedding_model=model_name
            )

            job.progress = 60 + int((start + len(batch)) / total * 15)
            job.save(update_fields=["progress"])
            self._notify(material, step="embeddings", progress=job.progress)

        self._update_collection(material, store)

    def _update_collection(self, material, store: VectorStorePort) -> None:
        from src.modules.projects.infrastructure.models import VectorCollection

        stats = store.stats()
        collection, _ = VectorCollection.objects.get_or_create(
            project_id=material.project_id,
            defaults={"index_path": f"{material.project.company.slug}/{material.project_id}"},
        )
        collection.mark_ready(
            count=stats.get("vector_count", 0),
            dimension=stats.get("dimension", 0) or self._embeddings.dimension,
            model=self._embeddings.model_name,
            provider=self._embeddings.provider_name,
        )

    # ═════════════════════════════════════════════════════════
    #  Etapa 5 · Análisis con LLM
    # ═════════════════════════════════════════════════════════
    def _analyze(self, material, blocks: list[SourceBlock], extras: dict) -> bool:
        """
        Ejecuta las cadenas de análisis. Devuelve True si alguna falló.

        Un fallo aquí NO invalida el material: los embeddings ya están y el chat
        funciona; el material queda `AVAILABLE` con `partial_analysis`.
        """
        from ...infrastructure.analysis import MaterialAnalyzer

        analyzer = MaterialAnalyzer(llm=self._llm)
        return analyzer.run(material, blocks, is_video=extras.get("is_video", False))

    # ═════════════════════════════════════════════════════════
    @staticmethod
    def _abort_if_deleted(material) -> None:
        """
        Corta el pipeline si el material se eliminó mientras se procesaba.

        Sin esto, borrar un material no libera su worker: la tarea sigue
        transcribiendo o llamando al LLM durante minutos y deja en cola las
        subidas siguientes, además de escribir artefactos huérfanos.
        """
        from src.modules.trainings.infrastructure.models import Material

        still_alive = Material.objects.filter(id=material.id).exists()
        if not still_alive:
            raise MaterialDeleted

    def _cleanup_orphan_results(self, material) -> None:
        """Elimina lo que la ingesta alcanzó a escribir antes de abortarse."""
        from ...infrastructure.models import Chunk

        Chunk.objects.filter(material_id=material.id).delete()
        try:
            self._vector_store_factory(material.project_id).delete_by_material(material.id)
        except Exception:  # pragma: no cover - el índice se reconstruye igual
            logger.warning(f"No se pudieron quitar los vectores de {material.id}")

    def _purge_previous_results(self, material) -> None:
        from ...infrastructure.models import Chapter, Chunk, Concept, Faq, Transcript

        Chunk.objects.filter(material=material).delete()
        Chapter.objects.filter(material=material).delete()
        Concept.objects.filter(material=material).delete()
        Faq.objects.filter(material=material).delete()
        Transcript.objects.filter(material=material).delete()
        material.summary = ""
        material.partial_analysis = False
        material.save(update_fields=["summary", "partial_analysis", "updated_at"])

    def _notify(self, material, *, step: str, progress: int) -> None:
        self._publisher.send_to_group(
            f"material.{material.id}",
            {
                "type": "material.status",
                "material_id": str(material.id),
                "status": material.status,
                "step": step,
                "progress": progress,
                "error_code": material.error_code or None,
            },
        )
