"""RF-036 · Búsqueda full-text dentro de una capacitación."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.postgres.search import SearchHeadline, SearchQuery, SearchRank, SearchVector

from .models import Chunk


@dataclass
class CourseSearchResult:
    material_id: str
    material_title: str
    material_type: str
    lesson_id: str
    excerpt: str
    start_time: float | None
    page: int | None
    rank: float


def search_course(training, query: str, *, limit: int = 25) -> list[CourseSearchResult]:
    """
    Busca en transcripciones y documentos del curso.

    Devuelve el extracto con el término resaltado y su ubicación exacta, para
    que el usuario salte directo al minuto o a la página.
    """
    search_query = SearchQuery(query, config="spanish", search_type="websearch")
    vector = SearchVector("content", config="spanish")

    rows = (
        Chunk.objects.filter(training=training)
        .select_related("material")
        .annotate(
            rank=SearchRank(vector, search_query),
            headline=SearchHeadline(
                "content",
                search_query,
                config="spanish",
                start_sel="<mark>",
                stop_sel="</mark>",
                max_words=45,
                min_words=20,
            ),
        )
        .filter(rank__gt=0.01)
        .order_by("-rank")[:limit]
    )

    return [
        CourseSearchResult(
            material_id=str(row.material_id),
            material_title=row.material.original_filename,
            material_type=row.material.type,
            lesson_id=str(row.material.lesson_id),
            excerpt=row.headline,
            start_time=row.start_time,
            page=row.page,
            rank=round(float(row.rank), 4),
        )
        for row in rows
    ]
