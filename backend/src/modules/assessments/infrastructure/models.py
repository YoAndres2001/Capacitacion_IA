"""Modelos ORM del módulo Assessments: exámenes, preguntas, intentos y respuestas."""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from src.modules.accounts.infrastructure.models import User
from src.modules.ai.infrastructure.models import Chunk
from src.modules.trainings.infrastructure.models import Material, Training
from src.shared.domain.exceptions import ExamNotPublishable, InvalidStateTransition
from src.shared.infrastructure.models import BaseModel


class Exam(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Borrador")
        PUBLISHED = "PUBLISHED", _("Publicado")
        ARCHIVED = "ARCHIVED", _("Archivado")

    class ScorePolicy(models.TextChoices):
        BEST = "BEST", _("Mejor intento")
        LAST = "LAST", _("Último intento")
        AVERAGE = "AVERAGE", _("Promedio")

    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name="exams")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )

    passing_score = models.PositiveSmallIntegerField(
        default=70, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    max_attempts = models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1)])
    time_limit_minutes = models.PositiveSmallIntegerField(default=0, help_text=_("0 = sin límite"))
    min_progress_required = models.PositiveSmallIntegerField(
        default=80, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    score_policy = models.CharField(
        max_length=20, choices=ScorePolicy.choices, default=ScorePolicy.BEST
    )
    shuffle_questions = models.BooleanField(default=True)

    generated_by_ai = models.BooleanField(default=False)
    generation_model = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_exams"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "exams"
        verbose_name = _("examen")
        verbose_name_plural = _("exámenes")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["training", "status"], name="idx_exam_training_status")]

    def __str__(self) -> str:
        return self.title

    # ── Reglas de negocio ────────────────────────────────────
    @property
    def total_points(self) -> Decimal:
        return self.questions.aggregate(total=models.Sum("points"))["total"] or Decimal("0")

    @property
    def has_attempts(self) -> bool:
        return self.attempts.exists()

    def can_edit_questions(self) -> bool:
        """RN-06/RN-08: un examen publicado con intentos queda congelado."""
        return not (self.status == self.Status.PUBLISHED and self.has_attempts)

    def publish(self) -> None:
        questions = list(self.questions.prefetch_related("options"))
        if not questions:
            raise ExamNotPublishable("El examen no tiene preguntas.")
        if self.total_points <= 0:
            raise ExamNotPublishable("La suma de puntos debe ser mayor que cero.")

        for question in questions:
            if not question.has_valid_answer_key():
                raise ExamNotPublishable(
                    f"La pregunta «{question.statement[:60]}...» no tiene respuesta correcta definida."
                )

        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at", "updated_at"])

    def archive(self) -> None:
        self.status = self.Status.ARCHIVED
        self.save(update_fields=["status", "updated_at"])


class Question(BaseModel):
    class Type(models.TextChoices):
        SINGLE_CHOICE = "SINGLE_CHOICE", _("Selección múltiple (una correcta)")
        MULTIPLE_CHOICE = "MULTIPLE_CHOICE", _("Selección múltiple (varias correctas)")
        TRUE_FALSE = "TRUE_FALSE", _("Verdadero / Falso")
        SHORT_ANSWER = "SHORT_ANSWER", _("Respuesta corta")
        OPEN_ENDED = "OPEN_ENDED", _("Pregunta abierta")

    class Level(models.TextChoices):
        BEGINNER = "BEGINNER", _("Principiante")
        INTERMEDIATE = "INTERMEDIATE", _("Intermedio")
        ADVANCED = "ADVANCED", _("Avanzado")

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    type = models.CharField(max_length=20, choices=Type.choices)
    statement = models.TextField()
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INTERMEDIATE)
    points = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("1.00"))
    order = models.PositiveIntegerField(default=0)

    explanation = models.TextField(blank=True, help_text=_("Por qué la respuesta correcta lo es."))
    correct_text = models.TextField(blank=True, help_text=_("Clave de respuesta corta/abierta."))
    rubric = models.JSONField(default=dict, blank=True, help_text=_("Criterios para preguntas abiertas."))

    # Trazabilidad al material: permite decir "repasa el minuto 14"
    source_chunk = models.ForeignKey(
        Chunk, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions"
    )
    source_material = models.ForeignKey(
        Material, on_delete=models.SET_NULL, null=True, blank=True, related_name="questions"
    )
    source_start_time = models.FloatField(null=True, blank=True)
    source_page = models.PositiveIntegerField(null=True, blank=True)

    generated_by_ai = models.BooleanField(default=False)

    class Meta:
        db_table = "questions"
        verbose_name = _("pregunta")
        verbose_name_plural = _("preguntas")
        ordering = ["order", "created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(points__gt=0), name="ck_points_positive")
        ]
        indexes = [models.Index(fields=["exam", "order"], name="idx_question_exam_order")]

    def __str__(self) -> str:
        return self.statement[:80]

    @property
    def is_closed(self) -> bool:
        return self.type in {
            self.Type.SINGLE_CHOICE,
            self.Type.MULTIPLE_CHOICE,
            self.Type.TRUE_FALSE,
        }

    def has_valid_answer_key(self) -> bool:
        if self.is_closed:
            correct = [option for option in self.options.all() if option.is_correct]
            if self.type in {self.Type.SINGLE_CHOICE, self.Type.TRUE_FALSE}:
                return len(correct) == 1
            return len(correct) >= 1
        return bool(self.correct_text.strip() or self.rubric)

    def review_hint(self) -> str:
        """Sugerencia de repaso con la ubicación exacta en el material (RF-066)."""
        if self.source_material_id is None:
            return ""
        title = self.source_material.original_filename
        if self.source_start_time is not None:
            return f"Repasa «{title}» desde el minuto {int(self.source_start_time // 60)}:{int(self.source_start_time % 60):02d}."
        if self.source_page is not None:
            return f"Repasa «{title}», página {self.source_page}."
        return f"Repasa el material «{title}»."


class QuestionOption(BaseModel):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    feedback = models.TextField(blank=True, help_text=_("Por qué esta opción es o no correcta."))

    class Meta:
        db_table = "question_options"
        ordering = ["order"]

    def __str__(self) -> str:
        return self.text[:60]


class Attempt(BaseModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", _("En curso")
        SUBMITTED = "SUBMITTED", _("Entregado")
        GRADING = "GRADING", _("Corrigiendo")
        GRADED = "GRADED", _("Corregido")
        EXPIRED = "EXPIRED", _("Vencido")

    #: transiciones válidas del intento
    TRANSITIONS = {
        Status.IN_PROGRESS: {Status.SUBMITTED, Status.EXPIRED},
        Status.SUBMITTED: {Status.GRADING},
        Status.GRADING: {Status.GRADED, Status.SUBMITTED},
        Status.GRADED: set(),
        Status.EXPIRED: set(),
    }

    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name="attempts")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True
    )

    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    passed = models.BooleanField(default=False)

    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    ai_feedback = models.TextField(blank=True)

    class Meta:
        db_table = "attempts"
        verbose_name = _("intento")
        verbose_name_plural = _("intentos")
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "user", "number"], name="uq_attempt_number"
            )
        ]
        indexes = [models.Index(fields=["user", "status"], name="idx_attempt_user")]

    def __str__(self) -> str:
        return f"{self.user} · {self.exam} (intento {self.number})"

    # ── Transiciones ─────────────────────────────────────────
    def _transition(self, target: str, **extra) -> None:
        if target not in self.TRANSITIONS.get(self.status, set()):
            raise InvalidStateTransition("Attempt", self.status, target)
        self.status = target
        for key, value in extra.items():
            setattr(self, key, value)
        self.save(update_fields=["status", "updated_at", *extra.keys()])

    def submit(self) -> None:
        self._transition(self.Status.SUBMITTED, submitted_at=timezone.now())

    def start_grading(self) -> None:
        self._transition(self.Status.GRADING)

    def apply_grade(self, *, obtained: Decimal, maximum: Decimal, passing_score: int) -> None:
        percentage = (obtained / maximum * 100) if maximum > 0 else Decimal("0")
        self.status = self.Status.GRADED
        self.score = obtained.quantize(Decimal("0.01"))
        self.max_score = maximum.quantize(Decimal("0.01"))
        self.passed = percentage >= passing_score
        self.graded_at = timezone.now()
        self.save(
            update_fields=["status", "score", "max_score", "passed", "graded_at", "updated_at"]
        )

    @property
    def percentage(self) -> float:
        if not self.max_score:
            return 0.0
        return round(float(self.score or 0) / float(self.max_score) * 100, 2)

    def is_expired(self) -> bool:
        limit = self.exam.time_limit_minutes
        if not limit or self.status != self.Status.IN_PROGRESS:
            return False
        elapsed = (timezone.now() - self.started_at).total_seconds() / 60
        return elapsed > limit


class Answer(BaseModel):
    class GradingMethod(models.TextChoices):
        DETERMINISTIC = "DETERMINISTIC", _("Automática exacta")
        LLM = "LLM", _("Evaluada por IA")
        MANUAL = "MANUAL", _("Revisión manual")

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")

    selected_option_ids = models.JSONField(default=list, blank=True)
    text_answer = models.TextField(blank=True)

    points_awarded = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    is_correct = models.BooleanField(default=False)
    feedback = models.TextField(blank=True)
    review_hint = models.TextField(blank=True)
    grading_method = models.CharField(
        max_length=20, choices=GradingMethod.choices, default=GradingMethod.DETERMINISTIC
    )
    needs_manual_review = models.BooleanField(default=False)

    class Meta:
        db_table = "answers"
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="uq_answer")
        ]

    def __str__(self) -> str:
        return f"Respuesta de {self.attempt_id} a {self.question_id}"
