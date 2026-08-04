"""Puerto de generación de embeddings."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingsPort(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensión del vector. Un cambio obliga a reconstruir el índice (RN-10)."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Vectoriza un lote de fragmentos. Los vectores vienen normalizados L2."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Vectoriza una consulta (algunos modelos usan un prefijo distinto)."""
