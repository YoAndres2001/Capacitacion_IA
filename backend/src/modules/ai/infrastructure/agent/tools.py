"""
Herramientas del agente tutor (docs/12-agente-ia.md §4).

Regla de seguridad fundamental: `training_id` y `user_id` **nunca** provienen
del LLM; se inyectan desde el estado, que a su vez viene del token. Así ninguna
instrucción escondida en el material puede sacar al agente de su alcance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from src.shared.infrastructure.logging import get_logger

from ...domain.rag_policies import RetrievedChunk

logger = get_logger("ai.agent.tools")


@dataclass
class ToolContext:
    """Alcance inmutable de la ejecución. Lo fija el servidor, no el modelo."""

    training_id: UUID
    project_id: UUID
    user_id: UUID
    retriever: Any


@dataclass
class ToolResult:
    payload: Any
    chunks: list[RetrievedChunk] = field(default_factory=list)
    summary: str = ""


# ─────────────────────────────────────────────────────────────
def search_knowledge(
    ctx: ToolContext, *, query: str, top_k: int = 8, material_id: str | None = None
) -> ToolResult:
    """Recuperación híbrida dentro de la capacitación."""
    chunks = ctx.retriever.retrieve(
        query,
        training_id=ctx.training_id,
        project_id=ctx.project_id,
        material_id=UUID(material_id) if material_id else None,
        top_k=top_k,
    )
    return ToolResult(
        payload=[
            {"label": chunk.label(), "content": chunk.content[:1200], "score": chunk.score}
            for chunk in chunks
        ],
        chunks=chunks,
        summary=f"{len(chunks)} fragmentos encontrados para «{query}».",
    )


def list_materials(ctx: ToolContext) -> ToolResult:
    """Inventario de material disponible de la capacitación."""
    from src.modules.trainings.infrastructure.models import Material

    materials = Material.objects.filter(
        lesson__module__training_id=ctx.training_id, status=Material.Status.AVAILABLE
    ).values("id", "original_filename", "type", "duration_seconds", "page_count")

    return ToolResult(
        payload=[
            {
                "material_id": str(row["id"]),
                "title": row["original_filename"],
                "type": row["type"],
                "duration_seconds": row["duration_seconds"],
                "pages": row["page_count"],
            }
            for row in materials
        ],
        summary=f"{len(materials)} materiales disponibles.",
    )


def get_material_summary(ctx: ToolContext, *, material_id: str) -> ToolResult:
    """Resumen ejecutivo y capítulos ya generados durante la ingesta."""
    from src.modules.trainings.infrastructure.models import Material

    material = _material_in_scope(ctx, material_id)
    if material is None:
        return ToolResult(payload=None, summary="Material no encontrado en esta capacitación.")

    chapters = [
        {
            "title": chapter.title,
            "summary": chapter.summary,
            "start": chapter.start_time,
            "end": chapter.end_time,
            "page_range": [chapter.start_page, chapter.end_page],
        }
        for chapter in material.chapters.all()
    ]
    return ToolResult(
        payload={"title": material.original_filename, "summary": material.summary, "chapters": chapters},
        summary=f"Resumen de «{material.original_filename}» con {len(chapters)} capítulos.",
    )


def get_transcript_range(
    ctx: ToolContext, *, material_id: str, start: float, end: float
) -> ToolResult:
    """Transcripción literal de un tramo: responde "lo del minuto 14"."""
    from ..models import TranscriptSegment

    material = _material_in_scope(ctx, material_id)
    if material is None or not hasattr(material, "transcript"):
        return ToolResult(payload=None, summary="Sin transcripción para ese material.")

    segments = TranscriptSegment.objects.filter(
        transcript=material.transcript, start_time__gte=max(0.0, start - 5), end_time__lte=end + 5
    ).order_by("start_time")

    text = " ".join(segment.text for segment in segments)
    return ToolResult(
        payload={"text": text, "start": start, "end": end, "material": material.original_filename},
        summary=f"Transcripción de {_mmss(start)} a {_mmss(end)}.",
    )


def get_document_page(ctx: ToolContext, *, material_id: str, page: int) -> ToolResult:
    """Texto de una página o diapositiva concreta."""
    from ..models import Chunk

    material = _material_in_scope(ctx, material_id)
    if material is None:
        return ToolResult(payload=None, summary="Material no encontrado.")

    chunks = Chunk.objects.filter(material=material, page=page).order_by("index")
    text = "\n".join(chunk.content for chunk in chunks)
    return ToolResult(
        payload={"page": page, "text": text, "material": material.original_filename},
        summary=f"Página {page} de «{material.original_filename}».",
    )


def get_concepts(ctx: ToolContext, *, material_id: str | None = None) -> ToolResult:
    from ..models import Concept

    queryset = Concept.objects.filter(material__lesson__module__training_id=ctx.training_id)
    if material_id:
        queryset = queryset.filter(material_id=material_id)

    concepts = list(queryset.order_by("-relevance")[:40])
    return ToolResult(
        payload=[
            {"name": c.name, "definition": c.definition, "relevance": c.relevance}
            for c in concepts
        ],
        summary=f"{len(concepts)} conceptos clave.",
    )


def find_timestamp(ctx: ToolContext, *, topic: str) -> ToolResult:
    """Momentos del video donde se trata un tema."""
    chunks = ctx.retriever.retrieve(
        topic, training_id=ctx.training_id, project_id=ctx.project_id, top_k=6
    )
    moments = [
        {
            "material": chunk.material_title,
            "material_id": str(chunk.material_id),
            "start_time": chunk.start_time,
            "label": chunk.label(),
            "preview": chunk.content[:200],
        }
        for chunk in chunks
        if chunk.start_time is not None
    ]
    return ToolResult(
        payload=moments, chunks=chunks, summary=f"{len(moments)} momentos relacionados con «{topic}»."
    )


def compare_materials(ctx: ToolContext, *, material_ids: list[str], aspect: str) -> ToolResult:
    """
    Compara dos o más materiales sobre un aspecto.

    Recupera en paralelo por material para que la comparación tenga contexto
    equilibrado de ambos lados, en vez de que gane el que más se parezca a la
    consulta.
    """
    per_material: dict[str, list[dict[str, Any]]] = {}
    all_chunks: list[RetrievedChunk] = []

    for material_id in material_ids[:4]:
        material = _material_in_scope(ctx, material_id)
        if material is None:
            continue
        chunks = ctx.retriever.retrieve(
            aspect,
            training_id=ctx.training_id,
            project_id=ctx.project_id,
            material_id=material.id,
            top_k=4,
        )
        all_chunks.extend(chunks)
        per_material[material.original_filename] = [
            {"label": chunk.label(), "content": chunk.content[:900]} for chunk in chunks
        ]

    return ToolResult(
        payload={"aspect": aspect, "materials": per_material},
        chunks=all_chunks,
        summary=f"Comparación de {len(per_material)} materiales sobre «{aspect}».",
    )


#: Registro de herramientas disponibles para el enrutador del agente.
TOOL_REGISTRY = {
    "search_knowledge": search_knowledge,
    "list_materials": list_materials,
    "get_material_summary": get_material_summary,
    "get_transcript_range": get_transcript_range,
    "get_document_page": get_document_page,
    "get_concepts": get_concepts,
    "find_timestamp": find_timestamp,
    "compare_materials": compare_materials,
}


# ── Interno ──────────────────────────────────────────────────
def _material_in_scope(ctx: ToolContext, material_id: str):
    """Garantiza que el material pertenece a la capacitación del contexto."""
    from src.modules.trainings.infrastructure.models import Material

    try:
        return Material.objects.filter(
            id=material_id,
            lesson__module__training_id=ctx.training_id,
            status=Material.Status.AVAILABLE,
        ).first()
    except (ValueError, TypeError):
        return None


def _mmss(seconds: float) -> str:
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    return f"{minutes:d}:{secs:02d}"
