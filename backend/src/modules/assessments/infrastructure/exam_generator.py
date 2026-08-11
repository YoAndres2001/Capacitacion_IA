"""
CU-13 · Generación automática de exámenes con IA.

Puntos clave del diseño:
- La selección de fragmentos **cubre capítulos**, no solo similitud: un examen
  debe evaluar todo el curso, no el minuto más "denso".
- La salida del LLM se valida con Pydantic y se descartan preguntas inválidas o
  semánticamente duplicadas.
- Cada pregunta guarda su chunk de origen → la retroalimentación puede decir
  exactamente qué minuto o página repasar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from django.db.models import Sum
from django.db.models.functions import Length
from pydantic import BaseModel, Field, ValidationError

from src.modules.ai.application.ports.llm import ChatMessage, LLMPort
from src.modules.ai.infrastructure.models import Chunk
from src.modules.ai.infrastructure.providers.parsing import strict_schema
from src.modules.ai.infrastructure.usage import record_usage
from src.shared.domain.exceptions import InsufficientContent
from src.shared.domain.value_object import TokenUsage
from src.shared.infrastructure.logging import get_logger

from ..domain.grading import tokens
from .models import Exam, Question, QuestionOption

logger = get_logger("assessments.generator")

#: Cuánto material hace falta para generar un examen.
#:
#: Se mide en CARACTERES de texto disponible, no en número de fragmentos. Contar
#: fragmentos parecía razonable pero medía el efecto de `CHUNK_SIZE_TOKENS`: con
#: fragmentos de 800 tokens, un video de 90 s y un PDF corto caben en uno cada
#: uno, y la capacitación quedaba bloqueada pese a tener contenido de sobra.
#: Peor aún, subir el tamaño de fragmento —que mejora el RAG— volvía la puerta
#: MÁS estricta sobre el mismo material.
#:
#: El requisito escala con las preguntas pedidas, que es la relación real: no es
#: lo mismo redactar 5 preguntas que 30 sobre el mismo texto.
MIN_CONTENT_CHARS_PER_QUESTION = 300

#: Piso absoluto: por debajo no hay examen que valga, se pidan las que se pidan.
MIN_CONTENT_CHARS = 1000

DUPLICATE_THRESHOLD = 0.75

#: Reparto de la barra de avance: un tramo fijo por preparar el material y el
#: resto repartido entre los lotes, que es donde se va todo el tiempo real.
PROGRESS_SETUP = 5
PROGRESS_BATCHES = 95 - PROGRESS_SETUP


def available_content_chars(training) -> int:
    """Caracteres de material procesado y disponible de una capacitación."""
    return (
        Chunk.objects.filter(training=training, material__status="AVAILABLE").aggregate(
            total=Sum(Length("content"))
        )["total"]
        or 0
    )


def max_questions_for(content_chars: int) -> int:
    """Cuántas preguntas sostiene ese volumen de material."""
    if content_chars < MIN_CONTENT_CHARS:
        return 0
    return max(1, content_chars // MIN_CONTENT_CHARS_PER_QUESTION)


def assert_enough_content(training, num_questions: int, *, chunks: list | None = None) -> None:
    """
    Falla si el material no da para las preguntas pedidas.

    La llama la vista ANTES de encolar la tarea, y también el generador. Que la
    vista lo compruebe no es una optimización: el aviso de fallo viaja por
    WebSocket y una tarea que muere en milisegundos lo emite antes de que el
    navegador llegue a suscribirse, dejando la barra de progreso viva para
    siempre. Lo que se sabe de antemano se responde de inmediato con un 4xx.
    """
    total = (
        sum(len(chunk.content) for chunk in chunks)
        if chunks is not None
        else available_content_chars(training)
    )
    posibles = max_questions_for(total)

    if posibles == 0:
        raise InsufficientContent(
            "La capacitación todavía no tiene material suficiente para generar una "
            "evaluación. Sube contenido y espera a que termine de procesarse.",
            details={"content_chars": total, "minimum": MIN_CONTENT_CHARS},
        )

    if num_questions > posibles:
        raise InsufficientContent(
            f"El material alcanza para unas {posibles} preguntas y se pidieron "
            f"{num_questions}. Reduce la cantidad o añade más contenido.",
            details={
                "content_chars": total,
                "requested": num_questions,
                "max_questions": posibles,
            },
        )


class OptionOut(BaseModel):
    text: str
    is_correct: bool = False
    feedback: str = ""


class QuestionOut(BaseModel):
    type: str
    statement: str
    level: str = "INTERMEDIATE"
    points: float = 1.0
    explanation: str = ""
    correct_text: str = ""
    options: list[OptionOut] = Field(default_factory=list)
    source_index: int | None = None


class QuestionsOut(BaseModel):
    questions: list[QuestionOut] = Field(default_factory=list)


#: Se calcula una vez al importar: el esquema no cambia entre llamadas.
_QUESTIONS_SCHEMA = strict_schema(QuestionsOut)


#: El MATERIAL va primero y la restricción se repite justo antes de la orden
#: final: con modelos pequeños, lo último que leen es lo que más pesa. Sin esta
#: estructura, el modelo genera preguntas de cultura general ignorando el curso.
GENERATION_PROMPT = """\
MATERIAL DE LA CAPACITACIÓN
===========================
{material}

===========================

Tu tarea: redactar preguntas de evaluación SOBRE EL MATERIAL DE ARRIBA.

DISTRIBUCIÓN SOLICITADA
{distribution}

REGLAS
- Cada pregunta debe poder responderse leyendo el MATERIAL de arriba, y solo con él.
- Está PROHIBIDO usar conocimiento general o inventar temas que no aparezcan en el MATERIAL.
- Usa las mismas palabras y conceptos del MATERIAL (nombres de procesos, clases, campos).
- Nivel: {level}. Idioma: español.
- SINGLE_CHOICE: 3 o 4 alternativas, exactamente UNA correcta.
- TRUE_FALSE: exactamente 2 alternativas ("Verdadero" y "Falso"), una correcta.
- MULTIPLE_CHOICE: 5 alternativas, entre 2 y 3 correctas.
- SHORT_ANSWER: `correct_text` con la respuesta esperada (máx. 15 palabras).
- OPEN_ENDED: `correct_text` con los puntos clave que debe cubrir la respuesta
  (máx. 30 palabras).
- Cada pregunta debe traer `explanation` y `source_index` con el número del
  fragmento del MATERIAL en el que se basa.
- No repitas ni parafrasees la misma idea dos veces.

SÉ BREVE. El presupuesto de salida es limitado y un JSON que se corta se
descarta entero:
- `statement`: máx. 25 palabras. No cites el MATERIAL, pregunta directamente.
- `explanation`: máx. 20 palabras. Una sola frase, sin citar el fragmento.
- `feedback` de cada alternativa: máx. 12 palabras. Puede quedar vacío ("").
- `text` de cada alternativa: máx. 12 palabras.

ANTES DE RESPONDER, verifica que cada enunciado mencione algo que aparece
literalmente en el MATERIAL de arriba. Si no aparece, descártalo y escribe otro.

Devuelve SOLO un objeto JSON con esta forma:
{{"questions": [{{"type": "SINGLE_CHOICE", "statement": "...", "level": "INTERMEDIATE",
  "points": 1.0, "explanation": "...", "correct_text": "",
  "options": [{{"text": "...", "is_correct": true, "feedback": "..."}}],
  "source_index": 3}}]}}
"""


@dataclass
class GenerationRequest:
    training: Any
    title: str
    num_questions: int = 10
    level: str = "INTERMEDIATE"
    distribution: dict[str, int] | None = None
    passing_score: int = 70
    max_attempts: int = 3
    time_limit_minutes: int = 0
    created_by: Any = None
    #: Se invoca tras cada lote con el avance. Con un modelo local en CPU esto
    #: tarda decenas de minutos, y con un proveedor remoto un 429 puede parar el
    #: lote un minuto: sin esto la interfaz no distingue "trabajando" de "colgado".
    on_progress: Callable[[dict[str, Any]], None] | None = None


class ExamGenerator:
    def __init__(self, llm: LLMPort) -> None:
        self._llm = llm

    def generate(self, request: GenerationRequest) -> Exam:
        chunks = self._select_chunks(request.training, request.num_questions)
        # Se revalida aquí aunque la vista ya lo haya comprobado: entre la
        # petición y la ejecución de la tarea el material pudo eliminarse.
        assert_enough_content(request.training, request.num_questions, chunks=chunks)

        distribution = request.distribution or self._default_distribution(request.num_questions)

        exam = Exam.objects.create(
            training=request.training,
            title=request.title,
            description=f"Evaluación generada automáticamente sobre «{request.training.title}».",
            status=Exam.Status.DRAFT,  # RN-06: requiere aprobación humana
            passing_score=request.passing_score,
            max_attempts=request.max_attempts,
            time_limit_minutes=request.time_limit_minutes,
            generated_by_ai=True,
            generation_model=self._llm.model_name,
            created_by=request.created_by,
        )

        total_usage = TokenUsage()
        seen_statements: list[set[str]] = []
        created = 0

        # Se generan en lotes pequeños en lugar de una sola llamada gigante.
        # Medido: un JSON de 2 preguntas tarda ~100 s en CPU; el mismo prompt
        # pidiendo 6 no vuelve dentro del timeout. Además cada lote recibe una
        # porción distinta del material, lo que mejora la cobertura del curso.
        batches = self._batches(distribution)
        self._report(request, exam, step="material", progress=PROGRESS_SETUP, questions=0)

        for index, batch in enumerate(batches, start=1):
            if created >= request.num_questions:
                break
            material = self._render_material(self._rotate(chunks, len(seen_statements)))
            parsed, usage = self._ask_llm(batch, request.level, material)
            total_usage = total_usage + usage
            created += self._persist(
                exam,
                parsed.questions,
                chunks,
                seen_statements,
                created,
                limit=request.num_questions - created,
            )
            self._report(
                request,
                exam,
                step="questions",
                progress=PROGRESS_SETUP + round(PROGRESS_BATCHES * index / len(batches)),
                questions=created,
            )

        self._report(request, exam, step="done", progress=100, questions=created)

        record_usage(
            usage=total_usage,
            purpose="EXAM_GENERATION",
            company_id=request.training.project.company_id,
            project_id=request.training.project_id,
            user_id=getattr(request.created_by, "id", None),
        )

        logger.info(
            f"Examen generado: {created}/{request.num_questions} preguntas "
            f"(examen {exam.id}, modelo {self._llm.model_name})"
        )
        return exam

    @staticmethod
    def _report(
        request: GenerationRequest,
        exam: Exam,
        *,
        step: str,
        progress: int,
        questions: int,
    ) -> None:
        """
        Publica el avance sin dejar que un fallo del canal aborte la generación:
        perder la barra de progreso es molesto, perder 40 minutos de trabajo no.
        """
        if request.on_progress is None:
            return
        try:
            request.on_progress(
                {
                    "exam_id": str(exam.id),
                    "step": step,
                    "progress": progress,
                    "questions": questions,
                    "total": request.num_questions,
                }
            )
        except Exception:
            logger.warning("No se pudo publicar el avance de la generación", exc_info=True)

    @staticmethod
    def _batches(distribution: dict[str, int]) -> list[dict[str, int]]:
        """
        Divide la distribución en lotes de como máximo `EXAM_BATCH_SIZE`
        preguntas, sin mezclar tipos dentro de un lote: pedirle un solo tipo por
        llamada es lo que un modelo pequeño resuelve con fiabilidad.
        """
        from django.conf import settings

        size = max(1, int(settings.AI_SETTINGS.get("EXAM_BATCH_SIZE", 2)))

        batches: list[dict[str, int]] = []
        for question_type, count in distribution.items():
            remaining = int(count)
            while remaining > 0:
                take = min(size, remaining)
                batches.append({question_type: take})
                remaining -= take
        return batches

    @staticmethod
    def _rotate(chunks: list[Chunk], offset: int) -> list[Chunk]:
        """Rota los fragmentos para que cada lote parta por una zona distinta."""
        if not chunks:
            return chunks
        position = offset % len(chunks)
        return chunks[position:] + chunks[:position]

    # ── Selección de contenido ───────────────────────────────
    @staticmethod
    def _select_chunks(training, num_questions: int) -> list[Chunk]:
        """
        Muestreo con cobertura: se reparten los fragmentos entre los capítulos
        (o uniformemente si no hay capítulos), de modo que el examen abarque
        todo el curso y no solo su primera parte.
        """
        queryset = (
            Chunk.objects.filter(training=training, material__status="AVAILABLE")
            .select_related("material", "chapter")
            .order_by("material_id", "index")
        )
        pool = list(queryset)
        if not pool:
            return []

        target = min(len(pool), max(num_questions * 2, 12))

        by_chapter: dict[str, list[Chunk]] = {}
        for chunk in pool:
            key = str(chunk.chapter_id or chunk.material_id)
            by_chapter.setdefault(key, []).append(chunk)

        selected: list[Chunk] = []
        per_group = max(1, target // len(by_chapter))
        for group in by_chapter.values():
            step = max(1, len(group) // per_group)
            selected.extend(group[::step][:per_group])

        if len(selected) < target:
            remaining = [chunk for chunk in pool if chunk not in selected]
            selected.extend(remaining[: target - len(selected)])

        return selected[:target]

    @staticmethod
    def _render_material(chunks: list[Chunk]) -> str:
        """
        Numera los fragmentos para que el modelo pueda referenciarlos en
        `source_index` y así trazar cada pregunta a su origen en el material.

        Respeta el mismo límite de contexto que las cadenas de análisis: con un
        modelo pequeño, un prompt enorme es la diferencia entre generar el
        examen y agotar el tiempo de espera.
        """
        from django.conf import settings

        limit = int(settings.AI_SETTINGS.get("ANALYSIS_MAX_CHARS", 6000))

        parts: list[str] = []
        used = 0
        for position, chunk in enumerate(chunks, start=1):
            location = ""
            if chunk.start_time is not None:
                location = f" · minuto {int(chunk.start_time // 60)}"
            elif chunk.page is not None:
                location = f" · página {chunk.page}"
            block = f"[{position}] ({chunk.material.original_filename}{location})\n{chunk.content}"
            if used + len(block) > limit:
                break
            parts.append(block)
            used += len(block)
        return "\n\n".join(parts)

    @staticmethod
    def _default_distribution(total: int) -> dict[str, int]:
        single = max(1, round(total * 0.5))
        true_false = max(1, round(total * 0.2))
        short = max(1, round(total * 0.2))
        open_ended = max(0, total - single - true_false - short)
        return {
            "SINGLE_CHOICE": single,
            "TRUE_FALSE": true_false,
            "SHORT_ANSWER": short,
            "OPEN_ENDED": open_ended,
        }

    # ── LLM ──────────────────────────────────────────────────
    def _ask_llm(
        self, distribution: dict[str, int], level: str, material: str
    ) -> tuple[QuestionsOut, TokenUsage]:
        prompt = GENERATION_PROMPT.format(
            distribution=json.dumps(distribution, ensure_ascii=False),
            level=level,
            material=material,
        )
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "Eres un diseñador instruccional experto. Creas evaluaciones rigurosas "
                    "basadas exclusivamente en el material entregado. Devuelves SIEMPRE JSON válido."
                ),
            ),
            ChatMessage(role="user", content=prompt),
        ]

        total_usage = TokenUsage()
        for attempt in (1, 2):
            try:
                # Con el esquema, el adaptador pide Structured Outputs si el
                # modelo configurado los admite; si no, degrada a modo JSON y
                # aquí sigue actuando la validación Pydantic con reintento.
                raw, usage = self._llm.generate_json(messages, schema=_QUESTIONS_SCHEMA)
                total_usage = total_usage + usage
            except ValueError as exc:
                # El modelo devolvió texto que no es JSON. Se reintenta una vez
                # con una instrucción correctiva antes de rendirse; sin esto la
                # tarea entera falla por una salida mal formada.
                logger.warning(f"Salida no parseable del modelo: {exc}")
                if attempt == 2:
                    return QuestionsOut(), total_usage
                messages.append(
                    ChatMessage(
                        role="user",
                        content="Tu respuesta no era JSON. Devuelve SOLO el objeto JSON pedido.",
                    )
                )
                continue

            try:
                if isinstance(raw, list):
                    raw = {"questions": raw}
                return QuestionsOut.model_validate(raw), total_usage
            except ValidationError as exc:
                if attempt == 2:
                    logger.warning("El modelo no produjo preguntas válidas")
                    return QuestionsOut(), total_usage
                messages.append(
                    ChatMessage(
                        role="user",
                        content=(
                            "El JSON anterior es inválido. Errores: "
                            f"{str(exc)[:400]}. Devuelve SOLO el JSON correcto."
                        ),
                    )
                )
        return QuestionsOut(), total_usage

    # ── Persistencia y validación ────────────────────────────
    def _persist(
        self,
        exam: Exam,
        questions: list[QuestionOut],
        chunks: list[Chunk],
        seen_statements: list[set[str]],
        start_order: int = 0,
        limit: int | None = None,
    ) -> int:
        """
        Persiste las preguntas válidas del lote, hasta `limit` como máximo.

        `seen_statements` se comparte entre lotes para que la deduplicación
        semántica funcione a lo largo de todo el examen, no solo dentro de una
        llamada.

        El tope es imprescindible: un modelo pequeño ignora la cantidad pedida y
        sigue redactando hasta agotar el presupuesto de tokens. Sin `limit`, un
        examen de 10 preguntas termina con 30.
        """
        valid_types = set(Question.Type.values)
        valid_levels = set(Question.Level.values)
        created = 0

        material_words = _material_vocabulary(chunks)

        for candidate in questions:
            if limit is not None and created >= limit:
                break
            question_type = candidate.type.strip().upper()
            if question_type not in valid_types:
                continue
            if not candidate.statement.strip():
                continue
            if self._is_duplicate(candidate.statement, seen_statements):
                continue
            # Una pregunta que no habla del material es peor que no tener
            # pregunta: evalúa algo que el estudiante nunca vio en el curso.
            if not _is_about_material(candidate, material_words):
                logger.warning(
                    f"Pregunta descartada por no provenir del material: "
                    f"{candidate.statement[:70]}"
                )
                continue

            options = self._normalize_options(question_type, candidate.options)
            if question_type in {"SINGLE_CHOICE", "MULTIPLE_CHOICE", "TRUE_FALSE"} and not options:
                continue
            if question_type in {"SHORT_ANSWER", "OPEN_ENDED"} and not candidate.correct_text.strip():
                continue

            source = self._source_for(candidate.source_index, chunks)

            question = Question.objects.create(
                exam=exam,
                type=question_type,
                statement=candidate.statement.strip(),
                level=candidate.level.upper() if candidate.level.upper() in valid_levels else "INTERMEDIATE",
                points=Decimal(str(max(0.25, candidate.points))),
                order=start_order + created,
                explanation=candidate.explanation,
                correct_text=candidate.correct_text,
                source_chunk=source,
                source_material=source.material if source else None,
                source_start_time=source.start_time if source else None,
                source_page=source.page if source else None,
                generated_by_ai=True,
            )

            QuestionOption.objects.bulk_create(
                [
                    QuestionOption(
                        question=question,
                        text=option.text.strip(),
                        is_correct=option.is_correct,
                        order=index,
                        feedback=option.feedback,
                    )
                    for index, option in enumerate(options)
                ]
            )

            seen_statements.append(tokens(candidate.statement))
            created += 1

        return created

    @staticmethod
    def _normalize_options(question_type: str, options: list[OptionOut]) -> list[OptionOut]:
        """Descarta combinaciones imposibles (p. ej. dos correctas en una de una sola)."""
        cleaned = [option for option in options if option.text.strip()]
        correct = [option for option in cleaned if option.is_correct]

        if question_type == "TRUE_FALSE":
            if len(cleaned) != 2 or len(correct) != 1:
                return []
            return cleaned
        if question_type == "SINGLE_CHOICE":
            if len(cleaned) < 3 or len(correct) != 1:
                return []
            return cleaned
        if question_type == "MULTIPLE_CHOICE":
            if len(cleaned) < 4 or len(correct) < 2 or len(correct) == len(cleaned):
                return []
            return cleaned
        return []

    @staticmethod
    def _is_duplicate(statement: str, seen: list[set[str]]) -> bool:
        candidate = tokens(statement)
        if not candidate:
            return True
        for previous in seen:
            if not previous:
                continue
            overlap = len(candidate & previous) / max(len(candidate), len(previous))
            if overlap >= DUPLICATE_THRESHOLD:
                return True
        return False

    @staticmethod
    def _source_for(index: int | None, chunks: list[Chunk]) -> Chunk | None:
        if index is None:
            return None
        position = index - 1  # el prompt numera desde 1
        if 0 <= position < len(chunks):
            return chunks[position]
        return None


# ─────────────────────────────────────────────────────────────
#  Anclaje de las preguntas al material (RN-04 aplicado a exámenes)
# ─────────────────────────────────────────────────────────────
#: Proporción mínima del vocabulario de la pregunta que debe existir en el
#: material. Se mide sobre enunciado + clave, no sobre los distractores, que
#: legítimamente pueden introducir términos nuevos.
MIN_MATERIAL_OVERLAP = 0.30


def _material_vocabulary(chunks: list[Chunk]) -> set[str]:
    from src.modules.ai.domain.rag_policies import AnswerGroundingVerifier

    return AnswerGroundingVerifier._content_words(" ".join(c.content for c in chunks))


def _is_about_material(candidate: QuestionOut, material_words: set[str]) -> bool:
    """
    Verifica que la pregunta trate realmente del contenido del curso.

    Sin este filtro, un modelo pequeño puede ignorar el material y generar
    preguntas de cultura general: se observó producir preguntas sobre
    neurociencia dentro de un curso de gestión de inventario.
    """
    from src.modules.ai.domain.rag_policies import AnswerGroundingVerifier

    if not material_words:
        return False

    relevant_text = " ".join(
        [
            candidate.statement,
            candidate.correct_text,
            *[option.text for option in candidate.options if option.is_correct],
        ]
    )
    question_words = AnswerGroundingVerifier._content_words(relevant_text)
    if not question_words:
        return False

    overlap = len(question_words & material_words) / len(question_words)
    return overlap >= MIN_MATERIAL_OVERLAP
