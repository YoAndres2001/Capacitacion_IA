"""
CU-15 · Corrección automática de un intento.

Estrategia mixta (RN-08):
- Cerradas y respuesta corta clara → determinístico (exacto, gratis, inmediato).
- Respuesta corta ambigua y preguntas abiertas → LLM con rúbrica.
- Toda respuesta incorrecta recibe explicación **y** la sección exacta a repasar.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from src.modules.ai.application.ports.llm import ChatMessage, LLMPort
from src.modules.ai.infrastructure.usage import record_usage
from src.shared.domain.value_object import TokenUsage
from src.shared.infrastructure.logging import get_logger

from ..domain.grading import AnswerMatcher, GradeResult
from .models import Answer, Attempt, Question

logger = get_logger("assessments.grader")


class RubricScore(BaseModel):
    score: float = Field(ge=0, le=1)
    is_correct: bool = False
    feedback: str = ""


OPEN_PROMPT = """\
Evalúa la respuesta de un estudiante según la clave y la rúbrica.

PREGUNTA
{statement}

CLAVE / PUNTOS QUE DEBE CUBRIR
{expected}

RESPUESTA DEL ESTUDIANTE
{answer}

INSTRUCCIONES
- `score` entre 0 y 1 según cuántos puntos clave cubre.
- `is_correct` es true solo si score >= 0.7.
- `feedback` en español, 1-3 frases: qué acertó y qué le faltó. Tono constructivo.
- No inventes contenido que no esté en la clave.

Devuelve SOLO: {{"score": 0.0, "is_correct": false, "feedback": "..."}}
"""


class AttemptGrader:
    def __init__(self, llm: LLMPort | None = None) -> None:
        self._llm = llm

    def grade(self, attempt: Attempt) -> Attempt:
        if attempt.status == Attempt.Status.SUBMITTED:
            attempt.start_grading()

        exam = attempt.exam
        questions = list(exam.questions.prefetch_related("options"))
        answers = {
            str(answer.question_id): answer
            for answer in Answer.objects.filter(attempt=attempt)
        }

        obtained = Decimal("0")
        maximum = Decimal("0")
        usage = TokenUsage()

        for question in questions:
            maximum += question.points
            answer = answers.get(str(question.id))

            if answer is None:
                # Pregunta no respondida: se registra en 0 para que el informe sea completo.
                Answer.objects.create(
                    attempt=attempt,
                    question=question,
                    points_awarded=Decimal("0"),
                    is_correct=False,
                    feedback="No respondida.",
                    review_hint=question.review_hint(),
                )
                continue

            result, method, chain_usage = self._grade_answer(question, answer)
            usage = usage + chain_usage

            answer.points_awarded = result.points
            answer.is_correct = result.is_correct
            answer.grading_method = method
            answer.feedback = result.feedback or self._default_feedback(question, result)
            answer.review_hint = "" if result.is_correct else question.review_hint()
            answer.needs_manual_review = method == Answer.GradingMethod.MANUAL
            answer.save(
                update_fields=[
                    "points_awarded", "is_correct", "grading_method",
                    "feedback", "review_hint", "needs_manual_review", "updated_at",
                ]
            )
            obtained += result.points

        attempt.apply_grade(
            obtained=obtained, maximum=maximum, passing_score=exam.passing_score
        )
        attempt.ai_feedback = self._overall_feedback(attempt)
        attempt.save(update_fields=["ai_feedback", "updated_at"])

        if usage.total_tokens:
            record_usage(
                usage=usage,
                purpose="EXAM_GRADING",
                company_id=exam.training.project.company_id,
                project_id=exam.training.project_id,
                user_id=attempt.user_id,
            )

        return attempt

    # ── Corrección por tipo ──────────────────────────────────
    def _grade_answer(
        self, question: Question, answer: Answer
    ) -> tuple[GradeResult, str, TokenUsage]:
        correct_ids = [
            str(option.id) for option in question.options.all() if option.is_correct
        ]
        selected = [str(value) for value in (answer.selected_option_ids or [])]

        if question.type in {Question.Type.SINGLE_CHOICE, Question.Type.TRUE_FALSE}:
            return (
                AnswerMatcher.grade_single_choice(selected, correct_ids, question.points),
                Answer.GradingMethod.DETERMINISTIC,
                TokenUsage(),
            )

        if question.type == Question.Type.MULTIPLE_CHOICE:
            return (
                AnswerMatcher.grade_multiple_choice(selected, correct_ids, question.points),
                Answer.GradingMethod.DETERMINISTIC,
                TokenUsage(),
            )

        if question.type == Question.Type.SHORT_ANSWER:
            result = AnswerMatcher.grade_short_answer(
                answer.text_answer, question.correct_text, question.points
            )
            # Zona gris: se pide una segunda opinión semántica al modelo.
            if result.partial and self._llm is not None:
                llm_result, usage = self._grade_with_llm(question, answer)
                if llm_result is not None:
                    return llm_result, Answer.GradingMethod.LLM, usage
            return result, Answer.GradingMethod.DETERMINISTIC, TokenUsage()

        # OPEN_ENDED
        if self._llm is None:
            return (
                GradeResult(False, Decimal("0"), "Pendiente de revisión manual."),
                Answer.GradingMethod.MANUAL,
                TokenUsage(),
            )

        llm_result, usage = self._grade_with_llm(question, answer)
        if llm_result is None:
            return (
                GradeResult(False, Decimal("0"), "Pendiente de revisión manual."),
                Answer.GradingMethod.MANUAL,
                usage,
            )
        return llm_result, Answer.GradingMethod.LLM, usage

    def _grade_with_llm(
        self, question: Question, answer: Answer
    ) -> tuple[GradeResult | None, TokenUsage]:
        if not answer.text_answer.strip():
            return GradeResult(False, Decimal("0"), "Sin respuesta."), TokenUsage()

        prompt = OPEN_PROMPT.format(
            statement=question.statement,
            expected=question.correct_text or str(question.rubric),
            answer=answer.text_answer[:2000],
        )
        try:
            raw, usage = self._llm.generate_json(
                [
                    ChatMessage(
                        role="system",
                        content="Eres un evaluador justo y riguroso. Devuelves SIEMPRE JSON válido.",
                    ),
                    ChatMessage(role="user", content=prompt),
                ]
            )
            parsed = RubricScore.model_validate(raw)
        except Exception as exc:
            # Si el modelo falla, la pregunta queda para revisión manual: nunca
            # se penaliza al estudiante por un problema de infraestructura.
            logger.warning("Corrección con LLM fallida", extra={"error": str(exc)[:200]})
            return None, TokenUsage()

        points = (question.points * Decimal(str(round(parsed.score, 4)))).quantize(Decimal("0.01"))
        return (
            GradeResult(
                is_correct=parsed.is_correct or parsed.score >= 0.7,
                points=points,
                feedback=parsed.feedback,
                partial=0 < parsed.score < 0.7,
            ),
            usage,
        )

    # ── Retroalimentación ────────────────────────────────────
    @staticmethod
    def _default_feedback(question: Question, result: GradeResult) -> str:
        if result.is_correct:
            return "Respuesta correcta."
        return question.explanation or "Revisa el material relacionado con esta pregunta."

    @staticmethod
    def _overall_feedback(attempt: Attempt) -> str:
        percentage = attempt.percentage
        wrong = attempt.answers.filter(is_correct=False).count()

        if attempt.passed:
            if percentage >= 90:
                return "Excelente desempeño. Dominas el contenido de la capacitación."
            return (
                f"Aprobaste con {percentage:.0f}%. "
                f"Revisa las {wrong} pregunta(s) que fallaste para reforzar."
            )
        return (
            f"Obtuviste {percentage:.0f}% y no alcanzaste el mínimo de "
            f"{attempt.exam.passing_score}%. Repasa las secciones indicadas en cada "
            "pregunta incorrecta y vuelve a intentarlo."
        )
