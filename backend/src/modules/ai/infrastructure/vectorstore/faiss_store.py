"""
Almacén vectorial FAISS · un índice por proyecto (RN-02).

Decisiones:
- Vectores normalizados L2 + `IndexFlatIP` ⇒ producto interno = similitud coseno.
- El tipo de índice se elige por tamaño (Flat → HNSW → IVFPQ), ver docs §11.5.
- Escritura atómica (tmp + `os.replace`) y bloqueo por proyecto: solo los
  workers escriben; el backend solo lee.
- **La fuente de verdad son los `chunks` en PostgreSQL**: el índice siempre se
  puede reconstruir (RN-10).
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any
from uuid import UUID

from django.conf import settings

from src.shared.domain.exceptions import DomainError
from src.shared.infrastructure.logging import get_logger

from ...application.ports.embeddings import EmbeddingsPort
from ...application.ports.vector_store import SearchHit, VectorRecord, VectorStorePort

logger = get_logger("ai.faiss")

_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()

HNSW_THRESHOLD = 50_000
IVF_THRESHOLD = 1_000_000


class IndexWriteFailed(DomainError):
    code = "INDEX_WRITE_FAILED"
    default_message = "No se pudo escribir el índice vectorial."


def _lock_for(key: str) -> threading.RLock:
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.RLock()
        return _locks[key]


class FaissVectorStore(VectorStorePort):
    def __init__(self, project_id: UUID | str, embeddings: EmbeddingsPort) -> None:
        self.project_id = str(project_id)
        self._embeddings = embeddings
        self._root: Path = Path(settings.RAG_SETTINGS["INDEX_ROOT"]) / self.project_id
        self._root.mkdir(parents=True, exist_ok=True)
        self._index = None
        self._mapping: dict[int, str] = {}   # faiss_id → chunk_id
        self._metadata: dict[str, dict[str, Any]] = {}
        self._loaded = False

    # ── Rutas ────────────────────────────────────────────────
    @property
    def _index_path(self) -> Path:
        return self._root / "index.faiss"

    @property
    def _mapping_path(self) -> Path:
        return self._root / "mapping.json"

    @property
    def _meta_path(self) -> Path:
        return self._root / "meta.json"

    # ── API pública ──────────────────────────────────────────
    def add(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        with _lock_for(self.project_id):
            self._ensure_loaded(dimension=len(records[0].vector))
            faiss, np = _import_faiss()

            vectors = np.array([r.vector for r in records], dtype="float32")
            next_id = (max(self._mapping) + 1) if self._mapping else 0
            ids = np.arange(next_id, next_id + len(records), dtype="int64")

            self._index.add_with_ids(vectors, ids)

            for faiss_id, record in zip(ids.tolist(), records):
                chunk_id = str(record.chunk_id)
                self._mapping[faiss_id] = chunk_id
                self._metadata[chunk_id] = record.metadata

            self.persist()

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        with _lock_for(self.project_id):
            self._ensure_loaded(dimension=len(query_vector))
            if self._index is None or self._index.ntotal == 0:
                return []

            faiss, np = _import_faiss()
            query = np.array([query_vector], dtype="float32")

            # Se pide de más porque el filtrado por metadatos ocurre después.
            fetch = min(self._index.ntotal, max(top_k * 5, top_k))
            scores, ids = self._index.search(query, fetch)

            hits: list[SearchHit] = []
            for score, faiss_id in zip(scores[0].tolist(), ids[0].tolist()):
                if faiss_id < 0:
                    continue
                chunk_id = self._mapping.get(faiss_id)
                if chunk_id is None:
                    continue
                metadata = self._metadata.get(chunk_id, {})
                if filters and not _matches(metadata, filters):
                    continue
                hits.append(
                    SearchHit(chunk_id=UUID(chunk_id), score=float(score), metadata=metadata)
                )
                if len(hits) >= top_k:
                    break
            return hits

    def delete_by_material(self, material_id: UUID) -> int:
        """
        Elimina los vectores de un material.

        `IndexIDMap2` sobre `IndexFlat` soporta `remove_ids`; en índices que no
        lo permiten se marca el proyecto para reconstrucción completa.
        """
        with _lock_for(self.project_id):
            self._ensure_loaded()
            if self._index is None:
                return 0

            faiss, np = _import_faiss()
            target = str(material_id)
            faiss_ids = [
                faiss_id
                for faiss_id, chunk_id in self._mapping.items()
                if self._metadata.get(chunk_id, {}).get("material_id") == target
            ]
            if not faiss_ids:
                return 0

            try:
                self._index.remove_ids(np.array(faiss_ids, dtype="int64"))
            except Exception:
                logger.warning(
                    "El índice no soporta borrado selectivo; requiere reconstrucción",
                    extra={"project_id": self.project_id},
                )
                return 0

            for faiss_id in faiss_ids:
                chunk_id = self._mapping.pop(faiss_id, None)
                if chunk_id:
                    self._metadata.pop(chunk_id, None)

            self.persist()
            return len(faiss_ids)

    def rebuild(self, records: list[VectorRecord]) -> None:
        """Reconstrucción atómica: el índice antiguo sigue sirviendo hasta el swap."""
        with _lock_for(self.project_id):
            faiss, np = _import_faiss()

            dimension = len(records[0].vector) if records else self._embeddings.dimension
            temp_dir = self._root.parent / f"{self.project_id}._tmp"
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            temp_dir.mkdir(parents=True, exist_ok=True)

            index = _build_index(faiss, dimension, len(records))
            mapping: dict[int, str] = {}
            metadata: dict[str, dict[str, Any]] = {}

            if records:
                vectors = np.array([r.vector for r in records], dtype="float32")
                ids = np.arange(len(records), dtype="int64")

                if not index.is_trained:
                    index.train(vectors)
                index.add_with_ids(vectors, ids)

                for faiss_id, record in zip(ids.tolist(), records):
                    chunk_id = str(record.chunk_id)
                    mapping[faiss_id] = chunk_id
                    metadata[chunk_id] = record.metadata

            try:
                faiss.write_index(index, str(temp_dir / "index.faiss"))
                (temp_dir / "mapping.json").write_text(
                    json.dumps({str(k): v for k, v in mapping.items()}), encoding="utf-8"
                )
                (temp_dir / "metadata.json").write_text(
                    json.dumps(metadata), encoding="utf-8"
                )
                (temp_dir / "meta.json").write_text(
                    json.dumps(
                        {
                            "model": self._embeddings.model_name,
                            "provider": self._embeddings.provider_name,
                            "dimension": dimension,
                            "count": len(records),
                            "index_type": type(index).__name__,
                        }
                    ),
                    encoding="utf-8",
                )
            except Exception as exc:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise IndexWriteFailed(str(exc)) from exc

            # Swap atómico
            backup = self._root.parent / f"{self.project_id}._old"
            shutil.rmtree(backup, ignore_errors=True)
            if self._root.exists():
                os.replace(self._root, backup)
            os.replace(temp_dir, self._root)
            shutil.rmtree(backup, ignore_errors=True)

            self._index, self._mapping, self._metadata = index, mapping, metadata
            self._loaded = True

            logger.info(
                "Índice reconstruido",
                extra={"project_id": self.project_id, "vectors": len(records)},
            )

    def stats(self) -> dict[str, Any]:
        with _lock_for(self.project_id):
            self._ensure_loaded()
            meta = {}
            if self._meta_path.exists():
                meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            return {
                "project_id": self.project_id,
                "vector_count": int(getattr(self._index, "ntotal", 0)),
                "dimension": meta.get("dimension", 0),
                "model": meta.get("model", ""),
                "provider": meta.get("provider", ""),
                "index_type": meta.get("index_type", ""),
                "path": str(self._root),
            }

    def persist(self) -> None:
        if self._index is None:
            return
        faiss, _ = _import_faiss()
        try:
            tmp_index = self._index_path.with_suffix(".faiss.tmp")
            faiss.write_index(self._index, str(tmp_index))
            os.replace(tmp_index, self._index_path)

            self._mapping_path.write_text(
                json.dumps({str(k): v for k, v in self._mapping.items()}), encoding="utf-8"
            )
            (self._root / "metadata.json").write_text(
                json.dumps(self._metadata), encoding="utf-8"
            )
            self._meta_path.write_text(
                json.dumps(
                    {
                        "model": self._embeddings.model_name,
                        "provider": self._embeddings.provider_name,
                        "dimension": int(getattr(self._index, "d", 0)),
                        "count": int(getattr(self._index, "ntotal", 0)),
                        "index_type": type(self._index).__name__,
                    }
                ),
                encoding="utf-8",
            )
        except Exception as exc:
            raise IndexWriteFailed(str(exc)) from exc

    # ── Interno ──────────────────────────────────────────────
    def _ensure_loaded(self, *, dimension: int | None = None) -> None:
        if self._loaded:
            return
        faiss, _ = _import_faiss()

        if self._index_path.exists():
            self._index = faiss.read_index(str(self._index_path))
            if self._mapping_path.exists():
                raw = json.loads(self._mapping_path.read_text(encoding="utf-8"))
                self._mapping = {int(k): v for k, v in raw.items()}
            metadata_path = self._root / "metadata.json"
            if metadata_path.exists():
                self._metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        else:
            self._index = _build_index(faiss, dimension or self._embeddings.dimension, 0)

        self._loaded = True


def _build_index(faiss, dimension: int, expected_count: int):
    """Elige el tipo de índice según el volumen esperado (docs §11.5)."""
    if expected_count > IVF_THRESHOLD:
        quantizer = faiss.IndexFlatIP(dimension)
        base = faiss.IndexIVFFlat(quantizer, dimension, 4096, faiss.METRIC_INNER_PRODUCT)
    elif expected_count > HNSW_THRESHOLD:
        base = faiss.IndexHNSWFlat(dimension, 32, faiss.METRIC_INNER_PRODUCT)
        base.hnsw.efSearch = 64
    else:
        base = faiss.IndexFlatIP(dimension)
    return faiss.IndexIDMap2(base)


def _matches(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        value = metadata.get(key)
        if isinstance(expected, (list, tuple, set)):
            if value not in {str(item) for item in expected}:
                return False
        elif str(value) != str(expected):
            return False
    return True


def _import_faiss():
    try:
        import faiss  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise IndexWriteFailed(
            "faiss-cpu/numpy no están instalados en este contenedor."
        ) from exc
    return faiss, np
