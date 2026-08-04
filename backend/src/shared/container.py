"""
Composition root · inyección de dependencias.

Único lugar del backend donde se decide QUÉ implementación concreta satisface
cada puerto. Cambiar de proveedor de IA, de almacén vectorial o de storage se
hace aquí (y por variables de entorno), sin tocar dominio ni aplicación.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from django.conf import settings

from src.shared.application.ports.event_publisher import EventPublisherPort
from src.shared.application.ports.notifier import NotifierPort
from src.shared.application.ports.storage import StoragePort

if TYPE_CHECKING:  # pragma: no cover
    from src.modules.ai.application.ports.embeddings import EmbeddingsPort
    from src.modules.ai.application.ports.extractor import DocumentExtractorPort
    from src.modules.ai.application.ports.llm import LLMPort
    from src.modules.ai.application.ports.transcriber import TranscriberPort
    from src.modules.ai.application.ports.vector_store import VectorStorePort


# ─────────────────────────────────────────────────────────────
#  Infraestructura transversal
# ─────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_storage() -> StoragePort:
    from src.shared.infrastructure.storage.local import LocalStorage

    backend = settings.STORAGE_SETTINGS["BACKEND"]
    if backend == "s3":  # pragma: no cover - requiere credenciales
        from src.shared.infrastructure.storage.s3 import S3Storage

        return S3Storage()
    return LocalStorage()


@lru_cache(maxsize=1)
def get_event_publisher() -> EventPublisherPort:
    from src.shared.infrastructure.events.publisher import RedisChannelPublisher

    return RedisChannelPublisher()


@lru_cache(maxsize=1)
def get_notifier() -> NotifierPort:
    from src.shared.infrastructure.email.notifier import EmailNotifier

    return EmailNotifier()


# ─────────────────────────────────────────────────────────────
#  IA · proveedor desacoplado (RF-047)
# ─────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_llm() -> "LLMPort":
    from src.modules.ai.infrastructure.providers.factory import AIProviderFactory

    return AIProviderFactory.create_llm()


@lru_cache(maxsize=1)
def get_embeddings() -> "EmbeddingsPort":
    from src.modules.ai.infrastructure.providers.factory import AIProviderFactory

    return AIProviderFactory.create_embeddings()


@lru_cache(maxsize=1)
def get_transcriber() -> "TranscriberPort":
    from src.modules.ai.infrastructure.transcription.faster_whisper import (
        FasterWhisperTranscriber,
    )

    return FasterWhisperTranscriber()


def get_document_extractor(material_type: str) -> "DocumentExtractorPort":
    from src.modules.ai.infrastructure.extraction.factory import ExtractorFactory

    return ExtractorFactory.for_type(material_type)


def get_vector_store(project_id) -> "VectorStorePort":
    """El almacén vectorial es POR PROYECTO (RN-02); no se cachea globalmente."""
    from src.modules.ai.infrastructure.vectorstore.faiss_store import FaissVectorStore

    return FaissVectorStore(project_id=project_id, embeddings=get_embeddings())


def reset_container() -> None:
    """Limpia las cachés (tests y recarga de configuración)."""
    for factory in (
        get_storage,
        get_event_publisher,
        get_notifier,
        get_llm,
        get_embeddings,
        get_transcriber,
    ):
        factory.cache_clear()  # type: ignore[attr-defined]
