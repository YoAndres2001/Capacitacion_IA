"""Puerto del almacén vectorial (FAISS hoy; pgvector o Qdrant mañana)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class VectorRecord:
    chunk_id: UUID
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchHit:
    chunk_id: UUID
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStorePort(ABC):
    @abstractmethod
    def add(self, records: list[VectorRecord]) -> None: ...

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchHit]: ...

    @abstractmethod
    def delete_by_material(self, material_id: UUID) -> int: ...

    @abstractmethod
    def rebuild(self, records: list[VectorRecord]) -> None:
        """Reconstruye el índice desde cero de forma atómica (CU-18)."""

    @abstractmethod
    def stats(self) -> dict[str, Any]: ...

    @abstractmethod
    def persist(self) -> None: ...
