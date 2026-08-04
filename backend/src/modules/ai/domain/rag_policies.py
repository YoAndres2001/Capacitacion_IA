"""
Políticas de dominio del RAG (lógica pura, sin IO).

Estas dos clases son el corazón del compromiso "la IA no inventa" (RN-04):
- `GroundingPolicy` decide si hay contexto suficiente para responder.
- `CitationPolicy` verifica que cada cita de la respuesta exista de verdad.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

NO_CONTEXT_ANSWER = (
    "No encuentro esa información en el material de esta capacitación. "
    "Te sugiero consultarlo con el instructor."
)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    material_id: UUID
    content: str
    score: float
    material_title: str = ""
    material_type: str = ""
    chapter_title: str = ""
    start_time: float | None = None
    end_time: float | None = None
    page: int | None = None

    def label(self) -> str:
        """Etiqueta legible de la cita: 'Sesión Inventario · 14:32' o 'Manual · pág. 23'."""
        if self.start_time is not None:
            return f"{self.material_title} · {_mmss(self.start_time)}"
        if self.page is not None:
            return f"{self.material_title} · pág. {self.page}"
        return self.material_title or "Material"


@dataclass(frozen=True)
class Citation:
    chunk_id: UUID
    material_id: UUID
    label: str
    score: float
    start_time: float | None = None
    page: int | None = None


@dataclass
class GroundingDecision:
    is_grounded: bool
    chunks: list[RetrievedChunk] = field(default_factory=list)
    reason: str = ""


class GroundingPolicy:
    """
    Decide si el contexto recuperado sostiene una respuesta.

    Si no lo sostiene, ni siquiera se llama al LLM: se devuelve la respuesta
    honesta. Esto evita alucinaciones y ahorra cómputo.
    """

    def __init__(
        self,
        *,
        min_score: float = 0.35,
        min_top_score: float = 0.45,
        min_chunks: int = 1,
    ) -> None:
        self.min_score = min_score
        self.min_top_score = min_top_score
        self.min_chunks = min_chunks

    def evaluate(self, chunks: list[RetrievedChunk]) -> GroundingDecision:
        if not chunks:
            return GroundingDecision(False, [], "sin resultados de búsqueda")

        relevant = [c for c in chunks if c.score >= self.min_score]
        if len(relevant) < self.min_chunks:
            return GroundingDecision(
                False, [], f"ningún fragmento supera el umbral {self.min_score}"
            )

        best = max(c.score for c in relevant)
        if best < self.min_top_score:
            return GroundingDecision(
                False, [], f"mejor coincidencia {best:.2f} < {self.min_top_score}"
            )

        return GroundingDecision(True, relevant, "")


class AnswerGroundingVerifier:
    """
    Red de seguridad posterior a la generación (RN-04).

    El prompt puede pedirle al modelo que use solo el CONTEXTO, pero un modelo
    pequeño a veces lo ignora y responde con su conocimiento propio. Esta
    política mide cuánto del vocabulario significativo de la respuesta aparece
    realmente en el contexto entregado: si la respuesta habla de otra cosa, se
    descarta y se devuelve la respuesta honesta.

    Es determinista, no cuesta tokens y no depende del proveedor.
    """

    #: Palabras vacías y de conexión; no aportan evidencia de fundamento.
    STOPWORDS = frozenset(
        """
        el la los las un una unos unas de del al y o que en a por para con se su sus
        es son fue era ser estar como mas más pero si no lo le les nos ni sobre entre
        cuando donde cual cuales quien este esta estos estas ese esa eso aquel tambien
        muy ya hay han has he ha hemos habia puede pueden debe deben cada todo todos
        toda todas otro otra otros otras tiene tienen tener sin desde hasta segun
        """.split()
    )

    def __init__(self, *, min_overlap: float = 0.45, min_content_words: int = 8) -> None:
        self.min_overlap = min_overlap
        self.min_content_words = min_content_words

    def is_supported(self, answer: str, chunks: list[RetrievedChunk]) -> bool:
        """True si la respuesta se apoya en el contexto entregado."""
        if not chunks:
            return False
        if NO_CONTEXT_ANSWER[:40] in answer:
            return True  # ya es la respuesta honesta

        answer_words = self._content_words(answer)
        # Respuestas muy cortas ("Sí", "No aplica") no se pueden medir así.
        if len(answer_words) < self.min_content_words:
            return True

        context_words = self._content_words(" ".join(chunk.content for chunk in chunks))
        if not context_words:
            return False

        overlap = len(answer_words & context_words) / len(answer_words)
        return overlap >= self.min_overlap

    @classmethod
    def _content_words(cls, text: str) -> set[str]:
        normalized = _strip_accents(text.lower())
        words = re.findall(r"[a-z0-9]{4,}", normalized)
        return {word for word in words if word not in cls.STOPWORDS}


def _strip_accents(text: str) -> str:
    import unicodedata

    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


CITATION_RE = re.compile(r"\[(\d{1,2})\]")


class CitationPolicy:
    """Valida y materializa las citas que el LLM incluyó en su respuesta."""

    @staticmethod
    def extract(answer: str, context_chunks: list[RetrievedChunk]) -> list[Citation]:
        """
        Devuelve solo las citas legítimas.

        Un `[7]` cuando solo se entregaron 5 fragmentos es una alucinación de
        referencia: se descarta.
        """
        citations: list[Citation] = []
        seen: set[UUID] = set()

        for raw in CITATION_RE.findall(answer):
            index = int(raw) - 1
            if not (0 <= index < len(context_chunks)):
                continue
            chunk = context_chunks[index]
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            citations.append(
                Citation(
                    chunk_id=chunk.chunk_id,
                    material_id=chunk.material_id,
                    label=chunk.label(),
                    score=chunk.score,
                    start_time=chunk.start_time,
                    page=chunk.page,
                )
            )
        return citations

    @staticmethod
    def sanitize(answer: str, context_size: int) -> str:
        """Elimina del texto las referencias a fragmentos inexistentes."""

        def replace(match: re.Match[str]) -> str:
            index = int(match.group(1))
            return match.group(0) if 1 <= index <= context_size else ""

        return CITATION_RE.sub(replace, answer).replace("  ", " ").strip()

    @staticmethod
    def infer_from_overlap(
        answer: str, context_chunks: list[RetrievedChunk], *, limit: int = 3
    ) -> list[Citation]:
        """
        Deduce las fuentes cuando el modelo no escribió los marcadores `[n]`.

        Los modelos pequeños suelen ignorar la instrucción de citar. En vez de
        dejar al usuario sin enlaces al minuto o la página, se identifican los
        fragmentos cuyo vocabulario aparece de verdad en la respuesta. No es una
        cita textual del modelo, pero sí una fuente real y verificable.
        """
        answer_words = AnswerGroundingVerifier._content_words(answer)
        if not answer_words:
            return []

        scored: list[tuple[float, RetrievedChunk]] = []
        for chunk in context_chunks:
            chunk_words = AnswerGroundingVerifier._content_words(chunk.content)
            if not chunk_words:
                continue
            overlap = len(answer_words & chunk_words) / len(answer_words)
            if overlap >= 0.15:
                scored.append((overlap, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            Citation(
                chunk_id=chunk.chunk_id,
                material_id=chunk.material_id,
                label=chunk.label(),
                score=chunk.score,
                start_time=chunk.start_time,
                page=chunk.page,
            )
            for _, chunk in scored[:limit]
        ]

    @staticmethod
    def needs_review(answer: str, citations: list[Citation]) -> bool:
        """
        Señal de calidad: respuesta afirmativa y extensa sin ninguna cita.

        No bloquea al usuario; alimenta la analítica de calidad del RAG.
        """
        if citations:
            return False
        return len(answer) > 200 and NO_CONTEXT_ANSWER not in answer


def _mmss(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:d}:{secs:02d}"
