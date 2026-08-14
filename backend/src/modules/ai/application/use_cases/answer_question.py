"""
CU-12 · Responder una pregunta con RAG.

Aquí se materializa la regla RN-04: **si no hay contexto suficiente, no se
llama al LLM** y se devuelve una respuesta honesta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from src.shared.application.use_case import UseCase
from src.shared.domain.exceptions import NotFoundError
from src.shared.domain.value_object import TokenUsage
from src.shared.infrastructure.logging import get_logger

from ...domain.rag_policies import (
    NO_CONTEXT_ANSWER,
    AnswerGroundingVerifier,
    Citation,
    CitationPolicy,
    GroundingPolicy,
)
from ..ports.llm import ChatMessage, LLMPort

logger = get_logger("ai.chat")


@dataclass(frozen=True)
class AnswerInput:
    session_id: UUID
    question: str
    user_id: UUID
    level: str = "intermediate"
    on_token: Callable[[str], None] | None = None


@dataclass
class AnswerOutput:
    message_id: UUID
    content: str
    grounded: bool
    citations: list[Citation] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)


class AnswerQuestionUseCase(UseCase[AnswerInput, AnswerOutput]):
    def __init__(self, *, llm: LLMPort, retriever_factory) -> None:
        self._llm = llm
        self._retriever_factory = retriever_factory

    def execute(self, data: AnswerInput) -> AnswerOutput:
        from ...infrastructure.models import ChatMessage as ChatMessageModel
        from ...infrastructure.models import ChatSession, MessageCitation
        from ...infrastructure.rag import prompts
        from ...infrastructure.usage import record_usage

        session = (
            ChatSession.objects.select_related("training__project__company")
            .filter(id=data.session_id)
            .first()
        )
        if session is None:
            raise NotFoundError("La conversación no existe.")

        training = session.training

        # Se persiste la pregunta antes de nada: si el proveedor cae, no se pierde.
        ChatMessageModel.objects.create(
            session=session, role=ChatMessageModel.Role.USER, content=data.question
        )
        session.last_message_at = timezone.now()
        if not session.title:
            session.title = data.question[:120]
        session.save(update_fields=["last_message_at", "title", "updated_at"])

        history = self._recent_history(session)

        # ── Recuperación ─────────────────────────────────────
        retriever = self._retriever_factory(training.project_id)
        search_query = self._rewrite(data.question, history)

        def search(query: str):
            return retriever.retrieve(
                query,
                training_id=None if training.cross_material_search else training.id,
                project_id=training.project_id,
            )

        chunks = search(search_query)

        policy = GroundingPolicy(
            min_score=settings.RAG_SETTINGS["MIN_SCORE"],
            min_top_score=settings.RAG_SETTINGS["MIN_TOP_SCORE"],
        )
        decision = policy.evaluate(chunks)

        # Segunda oportunidad para las preguntas que hablan del curso en vez de
        # su contenido («¿de qué trata?», «dame un ejemplo»): no comparten
        # vocabulario con ningún fragmento y se quedaban bajo el umbral, aunque
        # el material sí las responda. Se reescriben con el temario a la vista.
        # Solo se paga la llamada al LLM cuando la búsqueda directa ya falló, y
        # el prompt deja intactas las preguntas ajenas al temario, que siguen
        # recibiendo la respuesta honesta (RN-04).
        if not decision.is_grounded:
            grounded_query = self._rewrite_with_syllabus(data.question, training)
            if grounded_query and grounded_query != search_query:
                retry = search(grounded_query)
                retry_decision = policy.evaluate(retry)
                logger.info(
                    f"Reintento con el temario: grounded={retry_decision.is_grounded} "
                    f"scores={[round(c.score, 3) for c in retry]} query={grounded_query[:160]!r}",
                    extra={"training_id": str(training.id)},
                )
                if retry_decision.is_grounded:
                    chunks, decision = retry, retry_decision

        # ── Sin contexto: respuesta honesta, sin llamar al LLM ──
        if not decision.is_grounded:
            logger.info(
                "Pregunta sin contexto suficiente",
                extra={"training_id": str(training.id), "reason": decision.reason},
            )
            message = ChatMessageModel.objects.create(
                session=session,
                role=ChatMessageModel.Role.ASSISTANT,
                content=NO_CONTEXT_ANSWER,
                grounded=False,
                model=self._llm.model_name,
            )
            if data.on_token:
                data.on_token(NO_CONTEXT_ANSWER)
            self._flag_content_gap(training, data)
            return AnswerOutput(
                message_id=message.id, content=NO_CONTEXT_ANSWER, grounded=False
            )

        # ── Generación ───────────────────────────────────────
        context_chunks = decision.chunks
        messages = [
            ChatMessage(
                role="system",
                content=prompts.build_chat_system(
                    training_title=training.title,
                    project_name=training.project.name,
                    level=data.level,
                ),
            ),
            ChatMessage(
                role="user",
                content=prompts.build_chat_user(
                    context=prompts.build_context(context_chunks),
                    history_block=prompts.build_history_block(history),
                    question=data.question,
                ),
            ),
        ]

        answer, usage = self._generate(messages, data.on_token)

        # ── Verificación posterior (RN-04) ───────────────────
        # El prompt pide usar solo el contexto, pero un modelo pequeño puede
        # ignorarlo y responder de memoria. Se comprueba que la respuesta se
        # apoye realmente en los fragmentos entregados.
        grounded = AnswerGroundingVerifier().is_supported(answer, context_chunks)
        if not grounded:
            logger.info(
                "Respuesta descartada por no apoyarse en el material",
                extra={"training_id": str(training.id)},
            )
            answer = NO_CONTEXT_ANSWER

        # El modelo también puede reconocer por sí mismo que no sabe: en ese
        # caso la respuesta tampoco está fundamentada en el material.
        if NO_CONTEXT_ANSWER[:40] in answer:
            grounded = False
            context_chunks = []

        answer = CitationPolicy.sanitize(answer, len(context_chunks))
        citations = CitationPolicy.extract(answer, context_chunks)

        # Muchos modelos pequeños no escriben los marcadores [n]; se deducen las
        # fuentes por solapamiento para no dejar al usuario sin enlaces.
        if grounded and not citations:
            citations = CitationPolicy.infer_from_overlap(answer, context_chunks)

        needs_review = grounded and CitationPolicy.needs_review(answer, citations)

        message = ChatMessageModel.objects.create(
            session=session,
            role=ChatMessageModel.Role.ASSISTANT,
            content=answer,
            grounded=grounded,
            needs_review=needs_review,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency_ms=usage.latency_ms,
            model=self._llm.model_name,
        )

        MessageCitation.objects.bulk_create(
            [
                MessageCitation(
                    message=message,
                    chunk_id=citation.chunk_id,
                    material_id=citation.material_id,
                    label=citation.label,
                    start_time=citation.start_time,
                    page=citation.page,
                    score=citation.score,
                )
                for citation in citations
            ]
        )

        record_usage(
            usage=usage,
            purpose="CHAT",
            company_id=training.project.company_id,
            project_id=training.project_id,
            user_id=data.user_id,
        )

        if not grounded:
            self._flag_content_gap(training, data)

        return AnswerOutput(
            message_id=message.id,
            content=answer,
            grounded=grounded,
            citations=citations,
            usage=usage,
        )

    # ── Interno ──────────────────────────────────────────────
    def _generate(
        self, messages: list[ChatMessage], on_token: Callable[[str], None] | None
    ) -> tuple[str, TokenUsage]:
        if on_token is None:
            response = self._llm.generate(messages)
            return response.content, response.usage

        # Streaming: el consumer WebSocket entrega cada token al navegador.
        parts: list[str] = []
        for token in self._llm.stream(messages):
            parts.append(token)
            on_token(token)
        content = "".join(parts)
        return content, TokenUsage(
            completion_tokens=len(content) // 4,
            model=self._llm.model_name,
            provider=self._llm.provider_name,
        )

    def _rewrite(self, question: str, history: list[tuple[str, str]]) -> str:
        """
        Reescribe la pregunta como consulta autónoma usando el historial.

        Solo cuando hay historial y la pregunta es corta (probable pronombre:
        "¿y eso cómo se hace?"). Evita una llamada extra al LLM en el caso común.
        """
        if not history or len(question) > 120:
            return question

        from ...infrastructure.rag import prompts

        try:
            rendered = "\n".join(f"{role}: {content[:200]}" for role, content in history[-4:])
            response = self._llm.generate(
                [
                    ChatMessage(role="user", content=prompts.QUERY_REWRITE.format(
                        history=rendered, question=question
                    ))
                ],
                temperature=0.0,
                max_tokens=120,
            )
            rewritten = response.content.strip().strip('"')
            return rewritten or question
        except Exception:
            return question

    def _rewrite_with_syllabus(self, question: str, training) -> str:
        """
        Convierte una pregunta sobre el curso en una consulta con sus términos.

        El temario se arma con los capítulos y conceptos ya extraídos por la IA;
        si el material aún no los tiene, bastan los nombres de archivo.
        """
        from ...infrastructure.rag import prompts

        syllabus = self._syllabus(training)
        if not syllabus:
            return ""

        try:
            response = self._llm.generate(
                [
                    ChatMessage(
                        role="user",
                        content=prompts.QUERY_GROUNDING_REWRITE.format(
                            title=training.title, syllabus=syllabus, question=question
                        ),
                    )
                ],
                temperature=0.0,
                max_tokens=120,
            )
            return response.content.strip().strip('"')
        except Exception:
            logger.warning("No se pudo reescribir la consulta con el temario", exc_info=True)
            return ""

    @staticmethod
    def _syllabus(training, limit: int = 14) -> str:
        from src.modules.trainings.infrastructure.models import Material

        from ...infrastructure.models import Chapter, Concept

        materials = Material.objects.filter(lesson__module__training=training)
        terms = list(
            Chapter.objects.filter(material__in=materials).values_list("title", flat=True)[:limit]
        )
        terms += list(
            Concept.objects.filter(material__in=materials).values_list("name", flat=True)[
                : limit - len(terms)
            ]
        )
        if not terms:
            terms = [material.original_filename for material in materials[:limit]]
        return "; ".join(terms)

    @staticmethod
    def _recent_history(session, limit: int = 8) -> list[tuple[str, str]]:
        from ...infrastructure.models import ChatMessage as ChatMessageModel

        rows = list(
            ChatMessageModel.objects.filter(session=session)
            .exclude(role=ChatMessageModel.Role.SYSTEM)
            .order_by("-created_at")[: (limit * 2) + 1]
        )
        rows.reverse()
        rows = rows[:-1]  # la pregunta recién insertada aún no tiene respuesta

        # Solo se conservan los intercambios que sí se respondieron. Un turno
        # con la negativa por falta de contexto no aporta información y el
        # modelo lo imita: repetía «no encuentro esa información» aunque en
        # este intento sí hubiera contexto. La pregunta huérfana tampoco sirve.
        history: list[tuple[str, str]] = []
        question = None
        for row in rows:
            if row.role == ChatMessageModel.Role.USER:
                question = row
            else:
                if question is not None and row.grounded:
                    history += [(question.role, question.content), (row.role, row.content)]
                question = None
        return history[-limit:]

    @staticmethod
    def _flag_content_gap(training, data: AnswerInput) -> None:
        """Señal para el instructor: existe una brecha de contenido."""
        from src.shared.container import get_event_publisher
        from src.shared.domain.events import AIAnsweredWithoutContext

        try:
            get_event_publisher().publish(
                AIAnsweredWithoutContext(
                    training_id=training.id, user_id=data.user_id, question=data.question[:500]
                )
            )
        except Exception:  # pragma: no cover
            pass
