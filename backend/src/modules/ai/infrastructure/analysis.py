"""
Cadenas de análisis con LLM (etapa 5 del pipeline).

Cada cadena es independiente y su fallo se aísla: si los capítulos fallan, el
resumen igual se genera. Todas validan la salida con Pydantic, porque los
modelos locales pequeños son propensos a devolver JSON imperfecto.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from pydantic import BaseModel, Field, ValidationError

from src.shared.infrastructure.logging import get_logger

from ..application.ports.llm import ChatMessage, LLMPort
from ..domain.chunking import SourceBlock
from .rag import prompts
from .usage import record_usage

logger = get_logger("ai.analysis")


def max_content_chars() -> int:
    """
    Longitud del texto que reciben las cadenas de análisis.

    Es configurable porque marca la diferencia entre un análisis de 2 minutos y
    uno de 20 en un equipo sin GPU.
    """
    return int(settings.AI_SETTINGS.get("ANALYSIS_MAX_CHARS", 6000))


# ── Esquemas de salida ───────────────────────────────────────
class ChapterOut(BaseModel):
    title: str = Field(max_length=250)
    summary: str = ""
    start: float | None = None
    end: float | None = None
    start_page: int | None = None
    end_page: int | None = None


class ChaptersOut(BaseModel):
    chapters: list[ChapterOut] = Field(default_factory=list)


class SummaryOut(BaseModel):
    summary: str = ""


class ConceptOut(BaseModel):
    name: str = Field(max_length=200)
    definition: str = ""
    relevance: float = 0.5


class ConceptsOut(BaseModel):
    concepts: list[ConceptOut] = Field(default_factory=list)


class FaqOut(BaseModel):
    question: str
    answer: str


class FaqsOut(BaseModel):
    faqs: list[FaqOut] = Field(default_factory=list)


class CompactAnalysisOut(BaseModel):
    """Salida del análisis en una sola pasada, para material corto."""

    summary: str = ""
    concepts: list[ConceptOut] = Field(default_factory=list)
    faqs: list[FaqOut] = Field(default_factory=list)


def compact_threshold() -> int:
    """Bajo esta longitud de contenido se usa el análisis de una sola llamada."""
    return int(settings.AI_SETTINGS.get("COMPACT_ANALYSIS_CHARS", 5000))


class MaterialAnalyzer:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    def run(self, material, blocks: list[SourceBlock], *, is_video: bool) -> bool:
        """Devuelve True si el análisis quedó incompleto (parcial)."""
        content = compress(blocks, is_video=is_video)
        if not content.strip():
            return True

        # Un documento de una o dos páginas no tiene capítulos que detectar, y
        # ejecutar cuatro cadenas sobre él multiplica por cuatro el tiempo sin
        # aportar nada. Se resuelve en una sola llamada acotada.
        if len(content) <= compact_threshold():
            return self._analyze_compact(material, content)

        failures = 0
        failures += 0 if self._chapters(material, content, is_video, blocks) else 1
        failures += 0 if self._summary(material, content) else 1
        failures += 0 if self._concepts(material, content) else 1
        failures += 0 if self._faqs(material, content) else 1

        if failures:
            logger.warning(
                "Análisis parcial del material",
                extra={"material_id": str(material.id), "failed_chains": failures},
            )
        return failures > 0

    # ── Análisis compacto (material corto) ───────────────────
    def _analyze_compact(self, material, content: str) -> bool:
        from .models import Chapter, Concept, Faq

        logger.info(
            f"Análisis compacto ({len(content)} caracteres) del material {material.id}"
        )
        parsed = self._json_chain(
            material,
            prompts.COMPACT_ANALYSIS_PROMPT.format(content=content),
            CompactAnalysisOut,
            purpose="ANALYSIS",
            max_tokens=700,
        )
        if parsed is None:
            return True

        if parsed.summary:
            material.summary = parsed.summary
            material.save(update_fields=["summary", "updated_at"])

        Concept.objects.filter(material=material).delete()
        Concept.objects.bulk_create(
            [
                Concept(
                    material=material,
                    name=concept.name[:200],
                    definition=concept.definition,
                    relevance=max(0.0, min(1.0, concept.relevance)),
                )
                for concept in parsed.concepts
            ]
        )

        Faq.objects.filter(material=material).delete()
        Faq.objects.bulk_create(
            [
                Faq(material=material, question=faq.question, answer=faq.answer, order=index)
                for index, faq in enumerate(parsed.faqs)
            ]
        )

        # Un material corto es un único capítulo: se registra para que la
        # interfaz y las citas tengan siempre una referencia temática.
        Chapter.objects.filter(material=material).delete()
        Chapter.objects.create(
            material=material,
            order=0,
            title=material.original_filename,
            summary=parsed.summary[:500],
        )
        self._link_chunks_to_chapters(material)

        return not (parsed.summary or parsed.concepts or parsed.faqs)

    # ── Cadenas ──────────────────────────────────────────────
    def _chapters(self, material, content: str, is_video: bool, blocks: list[SourceBlock]) -> bool:
        from .models import Chapter

        parsed = self._json_chain(
            material,
            prompts.chapters_prompt(content, is_video=is_video),
            ChaptersOut,
            purpose="ANALYSIS",
            max_tokens=600,
        )
        if parsed is None:
            return False

        chapters = parsed.chapters
        if is_video:
            chapters = ground_chapter_times(chapters, blocks)

        Chapter.objects.filter(material=material).delete()
        Chapter.objects.bulk_create(
            [
                Chapter(
                    material=material,
                    order=index,
                    title=chapter.title[:250],
                    summary=chapter.summary,
                    start_time=chapter.start,
                    end_time=chapter.end,
                    start_page=chapter.start_page,
                    end_page=chapter.end_page,
                )
                for index, chapter in enumerate(chapters)
            ]
        )
        self._link_chunks_to_chapters(material)
        return True

    def _summary(self, material, content: str) -> bool:
        parsed = self._json_chain(
            material,
            prompts.SUMMARY_PROMPT.format(content=content),
            SummaryOut,
            purpose="ANALYSIS",
            max_tokens=400,
        )
        if parsed is None or not parsed.summary:
            return False
        material.summary = parsed.summary
        material.save(update_fields=["summary", "updated_at"])
        return True

    def _concepts(self, material, content: str) -> bool:
        from .models import Concept

        parsed = self._json_chain(
            material,
            prompts.CONCEPTS_PROMPT.format(content=content),
            ConceptsOut,
            purpose="ANALYSIS",
            max_tokens=600,
        )
        if parsed is None:
            return False

        Concept.objects.filter(material=material).delete()
        Concept.objects.bulk_create(
            [
                Concept(
                    material=material,
                    name=concept.name[:200],
                    definition=concept.definition,
                    relevance=max(0.0, min(1.0, concept.relevance)),
                )
                for concept in parsed.concepts
            ]
        )
        return True

    def _faqs(self, material, content: str) -> bool:
        from .models import Faq

        parsed = self._json_chain(
            material,
            prompts.FAQ_PROMPT.format(content=content),
            FaqsOut,
            purpose="ANALYSIS",
            max_tokens=700,
        )
        if parsed is None:
            return False

        Faq.objects.filter(material=material).delete()
        Faq.objects.bulk_create(
            [
                Faq(material=material, question=faq.question, answer=faq.answer, order=index)
                for index, faq in enumerate(parsed.faqs)
            ]
        )
        return True

    # ── Infra de las cadenas ─────────────────────────────────
    def _json_chain(
        self,
        material,
        prompt: str,
        schema: type[BaseModel],
        *,
        purpose: str,
        max_tokens: int | None = None,
    ):
        """
        Llama al LLM en modo JSON y valida con Pydantic.

        Un reintento correctivo cubre el caso típico del modelo pequeño que
        devuelve JSON casi válido.
        """
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "Eres un analista pedagógico. Devuelves SIEMPRE JSON válido, "
                    "sin texto adicional ni vallas de código. Sé conciso."
                ),
            ),
            ChatMessage(role="user", content=prompt),
        ]

        for attempt in (1, 2):
            try:
                raw, usage = self._llm.generate_json(messages, max_tokens=max_tokens)
                record_usage(
                    company_id=material.project.company_id,
                    project_id=material.project_id,
                    purpose=purpose,
                    usage=usage,
                )
                return schema.model_validate(_coerce(raw, schema))
            except ValidationError as exc:
                if attempt == 2:
                    logger.warning("Salida del LLM inválida", extra={"error": str(exc)[:300]})
                    return None
                messages.append(
                    ChatMessage(
                        role="user",
                        content=(
                            "La respuesta anterior no cumple el formato. "
                            f"Errores: {str(exc)[:400]}. Devuelve SOLO el JSON correcto."
                        ),
                    )
                )
            except Exception as exc:
                logger.warning("Fallo en la cadena de análisis", extra={"error": str(exc)[:300]})
                return None
        return None

    @staticmethod
    def _link_chunks_to_chapters(material) -> None:
        """Asocia cada chunk a su capítulo para poder citar el tema."""
        from .models import Chapter, Chunk

        chapters = list(Chapter.objects.filter(material=material))
        if not chapters:
            return

        for chunk in Chunk.objects.filter(material=material):
            match = None
            for chapter in chapters:
                if (
                    chunk.start_time is not None
                    and chapter.start_time is not None
                    and chapter.end_time is not None
                    and chapter.start_time <= chunk.start_time <= chapter.end_time
                ):
                    match = chapter
                    break
                if (
                    chunk.page is not None
                    and chapter.start_page is not None
                    and chapter.end_page is not None
                    and chapter.start_page <= chunk.page <= chapter.end_page
                ):
                    match = chapter
                    break
            if match is not None:
                Chunk.objects.filter(id=chunk.id).update(chapter=match)


def ground_chapter_times(chapters: list[ChapterOut], blocks: list[SourceBlock]) -> list[ChapterOut]:
    """
    Ancla los capítulos de un video a segmentos REALES de la transcripción.

    El prompt le muestra al modelo el contenido con marcas `[mm:ss]`, pero el
    modelo redondea, interpola y a veces inventa: un capítulo en el minuto 47 de
    un video de 30 haría que el reproductor saltara al vacío, y un `0:00` para
    todos los capítulos anula la navegación. Como los timestamps son la promesa
    central del producto ("esto está en el minuto 12:43"), no se aceptan tal
    cual.

    Cada `start` se desplaza al inicio de segmento real más cercano y cada `end`
    al fin de segmento real más cercano; los capítulos sin `start` utilizable se
    descartan. Si la transcripción no trae tiempos, se devuelve la lista intacta.
    """
    starts = sorted({b.start_time for b in blocks if b.start_time is not None})
    ends = sorted({b.end_time for b in blocks if b.end_time is not None})
    if not starts:
        return chapters

    grounded: list[ChapterOut] = []
    for chapter in chapters:
        if chapter.start is None:
            continue
        start = _nearest(starts, chapter.start)
        end = _nearest(ends, chapter.end) if chapter.end is not None and ends else None
        # Un capítulo que "termina" antes de empezar es ruido del modelo: se
        # deja sin fin en vez de guardar un rango imposible.
        if end is not None and end <= start:
            end = None
        grounded.append(chapter.model_copy(update={"start": start, "end": end}))

    if not grounded:
        logger.warning("El modelo no produjo capítulos con tiempos utilizables")
        return []

    # Dos capítulos que caen en el mismo segmento son el mismo capítulo.
    unique: list[ChapterOut] = []
    seen: set[float] = set()
    for chapter in sorted(grounded, key=lambda c: c.start or 0.0):
        if chapter.start in seen:
            continue
        seen.add(chapter.start)
        unique.append(chapter)
    return unique


def _nearest(values: list[float], target: float) -> float:
    return min(values, key=lambda value: abs(value - target))


def _coerce(raw: Any, schema: type[BaseModel]) -> Any:
    """
    Adapta salidas casi correctas.

    Es habitual que el modelo devuelva la lista desnuda (`[{...}]`) en lugar del
    objeto envolvente (`{"chapters": [...]}`): se envuelve en el único campo del
    esquema en vez de descartar un resultado válido.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list) and len(schema.model_fields) == 1:
        field_name = next(iter(schema.model_fields))
        return {field_name: raw}
    return raw


def compress(blocks: list[SourceBlock], *, is_video: bool, limit: int | None = None) -> str:
    """
    Reduce el material a un texto con marcas de ubicación que quepa en la ventana.

    Para materiales largos se muestrea uniformemente en lugar de truncar: así el
    análisis cubre el principio, el medio y el final del contenido.
    """

    def render(block: SourceBlock) -> str:
        if is_video and block.start_time is not None:
            return f"[{_mmss(block.start_time)}] {block.text.strip()}"
        if block.page is not None:
            return f"(pág. {block.page}) {block.text.strip()}"
        return block.text.strip()

    limit = limit or max_content_chars()

    rendered = [render(block) for block in blocks if block.text.strip()]
    joined = "\n".join(rendered)
    if len(joined) <= limit:
        return joined

    # Muestreo uniforme: se conserva una de cada `step` piezas.
    step = max(2, -(-len(joined) // limit))  # ceil(total / limit)
    sampled: list[str] = []
    used = 0
    for index in range(0, len(rendered), step):
        piece = rendered[index]
        if used + len(piece) > limit:
            break
        sampled.append(piece)
        used += len(piece)

    return "\n".join(sampled) or joined[:limit]


def _mmss(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"
