"""Modelos ORM del módulo Trainings: contenido, materiales, inscripción y progreso."""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from src.modules.accounts.infrastructure.models import User
from src.modules.projects.infrastructure.models import Project
from src.shared.domain.events import MaterialStatusChanged
from src.shared.infrastructure.models import BaseModel, BaseSoftDeleteModel

from ..domain.material_state import MaterialStateMachine, MaterialStatus


class Training(BaseSoftDeleteModel):
    """Capacitación (curso) dentro de un proyecto."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Borrador")
        PUBLISHED = "PUBLISHED", _("Publicada")
        ARCHIVED = "ARCHIVED", _("Archivada")

    class Level(models.TextChoices):
        BEGINNER = "BEGINNER", _("Principiante")
        INTERMEDIATE = "INTERMEDIATE", _("Intermedio")
        ADVANCED = "ADVANCED", _("Avanzado")

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="trainings")
    title = models.CharField(_("título"), max_length=200)
    slug = models.SlugField(max_length=220)
    description = models.TextField(blank=True)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.BEGINNER)
    cover_image = models.ImageField(upload_to="trainings/covers/", blank=True, null=True)
    estimated_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    chat_enabled = models.BooleanField(default=True)
    cross_material_search = models.BooleanField(
        default=False,
        help_text=_("Permite que el chat consulte todo el proyecto y no solo esta capacitación."),
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_trainings"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "trainings"
        verbose_name = _("capacitación")
        verbose_name_plural = _("capacitaciones")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "slug"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_training_slug",
            )
        ]
        indexes = [models.Index(fields=["project", "status"], name="idx_training_project_status")]

    def __str__(self) -> str:
        return self.title

    # ── Reglas de negocio ────────────────────────────────────
    def can_be_published(self) -> bool:
        """RN-05: al menos una lección con material disponible."""
        return Material.objects.filter(
            lesson__module__training=self, status=MaterialStatus.AVAILABLE
        ).exists()

    def publish(self) -> None:
        from src.shared.domain.exceptions import TrainingNotPublishable

        if not self.can_be_published():
            raise TrainingNotPublishable
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at", "updated_at"])

    def unpublish(self) -> None:
        self.status = self.Status.DRAFT
        self.save(update_fields=["status", "updated_at"])

    @property
    def total_lessons(self) -> int:
        return Lesson.objects.filter(module__training=self).count()


class Module(BaseModel):
    """Agrupación ordenada de lecciones."""

    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "modules"
        verbose_name = _("módulo")
        verbose_name_plural = _("módulos")
        ordering = ["order", "created_at"]
        indexes = [models.Index(fields=["training", "order"], name="idx_module_training_order")]

    def __str__(self) -> str:
        return f"{self.order}. {self.title}"


class Lesson(BaseModel):
    """Unidad mínima de consumo."""

    class Type(models.TextChoices):
        VIDEO = "VIDEO", _("Video")
        DOCUMENT = "DOCUMENT", _("Documento")
        TEXT = "TEXT", _("Texto")
        QUIZ = "QUIZ", _("Evaluación")

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.VIDEO)
    order = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    is_mandatory = models.BooleanField(default=True)
    content = models.TextField(blank=True, help_text=_("Contenido enriquecido para lecciones de texto."))

    class Meta:
        db_table = "lessons"
        verbose_name = _("lección")
        verbose_name_plural = _("lecciones")
        ordering = ["order", "created_at"]
        indexes = [models.Index(fields=["module", "order"], name="idx_lesson_module_order")]

    def __str__(self) -> str:
        return self.title

    @property
    def training_id(self):
        return self.module.training_id


class Material(BaseSoftDeleteModel):
    """
    Archivo asociado a una lección: es lo que procesa la IA.

    El campo `status` solo debe modificarse mediante los métodos de transición,
    que validan la máquina de estados del dominio.
    """

    class Type(models.TextChoices):
        VIDEO = "VIDEO", _("Video")
        PDF = "PDF", _("PDF")
        DOCX = "DOCX", _("Word")
        PPTX = "PPTX", _("PowerPoint")
        TXT = "TXT", _("Texto plano")
        MD = "MD", _("Markdown")
        AUDIO = "AUDIO", _("Audio")

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pendiente")
        PROCESSING = "PROCESSING", _("Procesando")
        ANALYZING = "ANALYZING", _("Analizando")
        AVAILABLE = "AVAILABLE", _("Disponible")
        ERROR = "ERROR", _("Error")

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="materials")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="materials")

    original_filename = models.CharField(max_length=255)
    file = models.CharField(max_length=500, help_text=_("Ruta relativa dentro del storage."))
    mime_type = models.CharField(max_length=120)
    size_bytes = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True)

    type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    error_code = models.CharField(max_length=60, blank=True)
    error_detail = models.TextField(blank=True)

    duration_seconds = models.PositiveIntegerField(default=0)
    page_count = models.PositiveIntegerField(default=0)
    thumbnail = models.CharField(max_length=500, blank=True)
    language = models.CharField(max_length=10, blank=True)

    summary = models.TextField(blank=True, help_text=_("Resumen ejecutivo generado por la IA."))
    partial_analysis = models.BooleanField(
        default=False, help_text=_("El RAG funciona, pero alguna cadena de análisis falló.")
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_materials"
    )

    class Meta:
        db_table = "materials"
        verbose_name = _("material")
        verbose_name_plural = _("materiales")
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "sha256"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_material_hash",
            )
        ]
        indexes = [
            models.Index(fields=["lesson"], name="idx_material_lesson"),
            models.Index(fields=["project", "status"], name="idx_material_project_status"),
        ]

    def __str__(self) -> str:
        return self.original_filename

    # ── Transiciones (delegan la validación al dominio) ──────
    def _transition(self, target: str, **extra) -> None:
        MaterialStateMachine.assert_transition(self.status, target)
        self.status = target
        fields = ["status", "updated_at", *extra.keys()]
        for key, value in extra.items():
            setattr(self, key, value)
        self.save(update_fields=fields)

    def mark_processing(self) -> None:
        self._transition(self.Status.PROCESSING, error_code="", error_detail="")

    def mark_analyzing(self) -> None:
        self._transition(self.Status.ANALYZING)

    def mark_available(self, *, partial: bool = False) -> None:
        self._transition(
            self.Status.AVAILABLE, processed_at=timezone.now(), partial_analysis=partial
        )

    def mark_error(self, code: str, detail: str = "") -> None:
        self._transition(self.Status.ERROR, error_code=code, error_detail=detail[:2000])

    def status_event(self, *, step: str = "", progress: int = 0) -> MaterialStatusChanged:
        return MaterialStatusChanged(
            material_id=self.id,
            status=self.status,
            step=step,
            progress=progress,
            error_code=self.error_code or None,
        )

    @property
    def is_queryable(self) -> bool:
        return MaterialStateMachine.is_queryable(self.status)

    @property
    def is_video(self) -> bool:
        return self.type in {self.Type.VIDEO, self.Type.AUDIO}


class ProcessingJob(BaseModel):
    """Traza de cada ejecución del pipeline de ingesta."""

    class Status(models.TextChoices):
        RUNNING = "RUNNING", _("En ejecución")
        SUCCESS = "SUCCESS", _("Completada")
        FAILED = "FAILED", _("Fallida")

    material = models.ForeignKey(
        Material, on_delete=models.CASCADE, related_name="processing_jobs"
    )
    celery_task_id = models.CharField(max_length=120, blank=True)
    step = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    progress = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "processing_jobs"
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["material", "-started_at"], name="idx_job_material")]

    def finish(self, *, success: bool, error: str = "") -> None:
        self.status = self.Status.SUCCESS if success else self.Status.FAILED
        self.progress = 100 if success else self.progress
        self.error = error[:2000]
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "progress", "error", "finished_at"])


class UploadSession(BaseModel):
    """Carga por trozos reanudable (CU-07)."""

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="upload_sessions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="upload_sessions")
    filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120)
    size_bytes = models.BigIntegerField()
    chunk_size = models.PositiveIntegerField()
    received_chunks = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField()
    completed = models.BooleanField(default=False)

    class Meta:
        db_table = "upload_sessions"
        indexes = [models.Index(fields=["user", "completed"], name="idx_upload_user")]

    @property
    def total_chunks(self) -> int:
        return max(1, -(-self.size_bytes // self.chunk_size))  # ceil

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at


# ─────────────────────────────────────────────────────────────
#  Aprendizaje
# ─────────────────────────────────────────────────────────────
class Enrollment(BaseModel):
    """Asignación de una capacitación a un usuario, con su progreso."""

    class Status(models.TextChoices):
        ASSIGNED = "ASSIGNED", _("Asignada")
        IN_PROGRESS = "IN_PROGRESS", _("En curso")
        COMPLETED = "COMPLETED", _("Completada")
        EXPIRED = "EXPIRED", _("Vencida")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enrollments")
    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ASSIGNED, db_index=True
    )
    progress = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_enrollments"
    )

    class Meta:
        db_table = "enrollments"
        verbose_name = _("inscripción")
        verbose_name_plural = _("inscripciones")
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "training"], name="uq_enrollment")
        ]
        indexes = [
            models.Index(fields=["training", "status"], name="idx_enrollment_status"),
            models.Index(fields=["user", "status"], name="idx_enrollment_user"),
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.training}"

    def recalculate_progress(self) -> None:
        """Deriva el avance del progreso por lección (nunca se asigna a mano)."""
        from ..domain.progress import LessonProgressSnapshot, ProgressCalculator

        lessons = Lesson.objects.filter(module__training_id=self.training_id)
        progress_map = {
            str(lp.lesson_id): lp
            for lp in LessonProgress.objects.filter(enrollment=self)
        }

        snapshots = [
            LessonProgressSnapshot(
                lesson_id=str(lesson.id),
                is_mandatory=lesson.is_mandatory,
                completed=getattr(progress_map.get(str(lesson.id)), "completed", False),
                watched_seconds=getattr(progress_map.get(str(lesson.id)), "watched_seconds", 0),
                duration_seconds=lesson.duration_seconds,
            )
            for lesson in lessons
        ]

        value = ProgressCalculator.compute(snapshots)
        fields = ["progress", "status", "updated_at"]
        self.progress = value

        if value >= 100 and self.status != self.Status.COMPLETED:
            self.status = self.Status.COMPLETED
            self.completed_at = timezone.now()
            fields.append("completed_at")
        elif 0 < value < 100:
            self.status = self.Status.IN_PROGRESS
            if self.started_at is None:
                self.started_at = timezone.now()
                fields.append("started_at")

        self.save(update_fields=fields)


class LessonProgress(BaseModel):
    """Avance de un usuario en una lección concreta."""

    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.CASCADE, related_name="lesson_progress"
    )
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress_records")
    completed = models.BooleanField(default=False)
    position_seconds = models.PositiveIntegerField(default=0)
    watched_seconds = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "lesson_progress"
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "lesson"], name="uq_lesson_progress")
        ]

    def mark_completed(self) -> None:
        if self.completed:
            return
        self.completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=["completed", "completed_at", "updated_at"])


class Note(BaseModel):
    """Nota personal del estudiante, opcionalmente anclada a un segundo del video."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notes")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="notes")
    content = models.TextField()
    timestamp_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "notes"
        ordering = ["timestamp_seconds", "created_at"]
        indexes = [models.Index(fields=["user", "lesson"], name="idx_note_user_lesson")]
