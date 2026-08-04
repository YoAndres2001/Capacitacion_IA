"""Tareas Celery del módulo de evaluaciones."""

from __future__ import annotations

from celery import shared_task

from src.shared.container import get_event_publisher, get_llm
from src.shared.domain.events import AttemptGraded
from src.shared.domain.exceptions import DomainError
from src.shared.infrastructure.logging import get_logger

logger = get_logger("assessments.tasks")


def _notify(user_id, payload: dict) -> None:
    """Envía al creador el desenlace de una tarea larga; sin él la UI se queda esperando."""
    if user_id is None:
        return
    get_event_publisher().send_to_group(
        f"user.{user_id}", {"type": "notification.message", **payload}
    )


@shared_task(name="assessments.generate_exam", bind=True, queue="ai", max_retries=1)
def generate_exam(self, training_id: str, options: dict) -> dict:
    """CU-13 · Genera un examen en estado DRAFT a partir del material."""
    from src.modules.accounts.infrastructure.models import User
    from src.modules.trainings.infrastructure.models import Training

    from .exam_generator import ExamGenerator, GenerationRequest

    training = Training.objects.select_related("project__company").get(id=training_id)
    created_by = (
        User.objects.filter(id=options.get("created_by")).first()
        if options.get("created_by")
        else None
    )
    user_id = getattr(created_by, "id", None)

    def report(payload: dict) -> None:
        _notify(
            user_id,
            {
                "event": "exam.generation_progress",
                "training_id": str(training.id),
                **payload,
            },
        )

    try:
        exam = ExamGenerator(llm=get_llm()).generate(
            GenerationRequest(
                training=training,
                title=options.get("title") or f"Evaluación · {training.title}",
                num_questions=int(options.get("num_questions", 10)),
                level=options.get("level", "INTERMEDIATE"),
                distribution=options.get("distribution"),
                passing_score=int(options.get("passing_score", 70)),
                max_attempts=int(options.get("max_attempts", 3)),
                time_limit_minutes=int(options.get("time_limit_minutes", 0)),
                created_by=created_by,
                on_progress=report if user_id else None,
            )
        )
    except DomainError as error:
        # Falta de material, proveedor caído: el motivo es accionable por el
        # usuario, así que se le entrega tal cual.
        logger.warning(f"Generación de examen fallida ({error.code}): {error.message}")
        _notify(
            user_id,
            {
                "event": "exam.generation_failed",
                "training_id": str(training.id),
                "code": error.code,
                "message": error.message,
            },
        )
        raise
    except Exception as error:
        logger.exception("Generación de examen interrumpida por un error inesperado")
        _notify(
            user_id,
            {
                "event": "exam.generation_failed",
                "training_id": str(training.id),
                "code": "UNEXPECTED_ERROR",
                "message": f"La generación se interrumpió: {error}",
            },
        )
        raise

    questions = exam.questions.count()

    # Un examen sin preguntas es un fallo aunque la tarea haya terminado bien:
    # el modelo no produjo nada aprovechable y el usuario debe saberlo.
    _notify(
        user_id,
        {
            "event": "exam.generated" if questions else "exam.generation_failed",
            "exam_id": str(exam.id),
            "training_id": str(training.id),
            "questions": questions,
            **(
                {}
                if questions
                else {
                    "code": "NO_QUESTIONS_GENERATED",
                    "message": (
                        "El modelo no produjo preguntas válidas sobre el material. "
                        "Intente con más contenido o un modelo mayor."
                    ),
                }
            ),
        },
    )

    return {
        "exam_id": str(exam.id),
        "questions": questions,
        "status": exam.status,
    }


@shared_task(name="assessments.grade_attempt", bind=True, queue="ai", max_retries=2)
def grade_attempt(self, attempt_id: str) -> dict:
    """CU-15 · Corrige un intento entregado."""
    from .grader import AttemptGrader
    from .models import Attempt

    attempt = Attempt.objects.select_related("exam__training__project").get(id=attempt_id)
    graded = AttemptGrader(llm=get_llm()).grade(attempt)

    publisher = get_event_publisher()
    publisher.publish(
        AttemptGraded(
            attempt_id=graded.id,
            user_id=graded.user_id,
            exam_id=graded.exam_id,
            score=graded.percentage,
            passed=graded.passed,
        )
    )
    publisher.send_to_group(
        f"user.{graded.user_id}",
        {
            "type": "notification.message",
            "event": "attempt.graded",
            "attempt_id": str(graded.id),
            "score": graded.percentage,
            "passed": graded.passed,
        },
    )

    return {"attempt_id": str(graded.id), "score": graded.percentage, "passed": graded.passed}


@shared_task(name="assessments.expire_attempts", queue="default")
def expire_attempts() -> dict:
    """Tarea programada: cierra intentos que superaron su tiempo límite."""
    from .models import Attempt

    expired = 0
    running = Attempt.objects.filter(status=Attempt.Status.IN_PROGRESS).select_related("exam")

    for attempt in running:
        if attempt.is_expired():
            attempt.submit()
            grade_attempt.delay(str(attempt.id))
            expired += 1

    return {"expired": expired}
