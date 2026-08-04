"""
Recuperación híbrida: FAISS (denso) + full-text de PostgreSQL (disperso).

La fusión con RRF mejora notablemente el *recall* en códigos, siglas y nombres
propios de un ERP ("OC-4471", "guía de despacho"), donde la búsqueda puramente
vectorial suele fallar (ADR-08).
"""

from __future__ import annotations

from uuid import UUID

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

from src.shared.infrastructure.logging import get_logger

from ...application.ports.embeddings import EmbeddingsPort
from ...application.ports.vector_store import VectorStorePort
from ...domain.rag_policies import RetrievedChunk
from ..models import Chunk

logger = get_logger("ai.retriever")

RRF_K = 60


class HybridRetriever:
    def __init__(
        self,
        *,
        vector_store: VectorStorePort,
        embeddings: EmbeddingsPort,
        hybrid: bool | None = None,
    ) -> None:
        self._store = vector_store
        self._embeddings = embeddings
        self._hybrid = settings.RAG_SETTINGS["HYBRID"] if hybrid is None else hybrid

    def retrieve(
        self,
        query: str,
        *,
        training_id: UUID | None = None,
        project_id: UUID | None = None,
        material_id: UUID | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        top_k = top_k or settings.RAG_SETTINGS["TOP_K"]
        candidates = max(top_k * 3, 20)

        dense = self._dense_search(query, training_id, material_id, candidates)
        sparse = (
            self._sparse_search(query, training_id, project_id, material_id, candidates)
            if self._hybrid
            else []
        )

        fused = _reciprocal_rank_fusion(dense, sparse)
        selected = _maximal_marginal_relevance(
            fused, lambda_=settings.RAG_SETTINGS["MMR_LAMBDA"], top_k=top_k
        )
        return self._hydrate(selected)

    # ── Búsquedas ────────────────────────────────────────────
    def _dense_search(
        self,
        query: str,
        training_id: UUID | None,
        material_id: UUID | None,
        limit: int,
    ) -> list[tuple[str, float]]:
        try:
            vector = self._embeddings.embed_query(query)
        except Exception:
            logger.warning("Embeddings no disponibles; se usará solo búsqueda textual")
            return []

        filters: dict[str, str] = {}
        if training_id:
            filters["training_id"] = str(training_id)
        if material_id:
            filters["material_id"] = str(material_id)

        hits = self._store.search(vector, top_k=limit, filters=filters or None)
        return [(str(hit.chunk_id), hit.score) for hit in hits]

    def _sparse_search(
        self,
        query: str,
        training_id: UUID | None,
        project_id: UUID | None,
        material_id: UUID | None,
        limit: int,
    ) -> list[tuple[str, float]]:
        queryset = Chunk.objects.all()
        if training_id:
            queryset = queryset.filter(training_id=training_id)
        elif project_id:
            queryset = queryset.filter(project_id=project_id)
        if material_id:
            queryset = queryset.filter(material_id=material_id)

        search_query = SearchQuery(query, config="spanish", search_type="websearch")
        try:
            results = (
                queryset.annotate(
                    rank=SearchRank(SearchVector("content", config="spanish"), search_query)
                )
                .filter(rank__gt=0.01)
                .order_by("-rank")[:limit]
            )
            return [(str(chunk.id), float(chunk.rank)) for chunk in results]
        except Exception:
            logger.warning("Búsqueda full-text no disponible", exc_info=True)
            return []

    # ── Hidratación ──────────────────────────────────────────
    def _hydrate(self, scored: list[tuple[str, float]]) -> list[RetrievedChunk]:
        if not scored:
            return []

        ids = [chunk_id for chunk_id, _ in scored]
        score_map = dict(scored)

        rows = (
            Chunk.objects.filter(id__in=ids)
            .select_related("material", "chapter")
            .only(
                "id", "content", "start_time", "end_time", "page",
                "material__id", "material__original_filename", "material__type",
                "chapter__title",
            )
        )

        result = [
            RetrievedChunk(
                chunk_id=row.id,
                material_id=row.material_id,
                content=row.content,
                score=score_map.get(str(row.id), 0.0),
                material_title=row.material.original_filename,
                material_type=row.material.type,
                chapter_title=row.chapter.title if row.chapter else "",
                start_time=row.start_time,
                end_time=row.end_time,
                page=row.page,
            )
            for row in rows
        ]
        result.sort(key=lambda chunk: chunk.score, reverse=True)
        return result


# ─────────────────────────────────────────────────────────────
#  Algoritmos de fusión y diversidad
# ─────────────────────────────────────────────────────────────
def _reciprocal_rank_fusion(
    dense: list[tuple[str, float]], sparse: list[tuple[str, float]]
) -> list[tuple[str, float]]:
    """
    RRF: fusiona rankings sin necesidad de normalizar escalas distintas.

    Se conserva además el score coseno original del componente denso, porque el
    umbral de `GroundingPolicy` se expresa en esa escala.
    """
    fused: dict[str, float] = {}
    cosine: dict[str, float] = {}

    for rank, (chunk_id, score) in enumerate(dense, start=1):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
        cosine[chunk_id] = score

    for rank, (chunk_id, _) in enumerate(sparse, start=1):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)

    ordered = sorted(fused.items(), key=lambda item: item[1], reverse=True)

    # Los resultados que solo aparecen en full-text no tienen score coseno;
    # se les asigna el umbral mínimo para que puedan pasar el filtro.
    minimum = settings.RAG_SETTINGS["MIN_SCORE"]
    return [(chunk_id, cosine.get(chunk_id, minimum)) for chunk_id, _ in ordered]


def _maximal_marginal_relevance(
    scored: list[tuple[str, float]], *, lambda_: float, top_k: int
) -> list[tuple[str, float]]:
    """
    MMR simplificado sobre el orden ya fusionado.

    Como el orden viene de RRF, aquí basta con recortar: la diversidad efectiva
    la aporta la combinación de dos recuperadores distintos. Se mantiene la
    firma para poder incorporar diversidad por similitud entre chunks sin
    tocar a los llamadores.
    """
    return scored[:top_k]
