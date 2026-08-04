"""Modelos ORM del módulo AI: artefactos del análisis, RAG y chat."""

from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils.translation import gettext_lazy as _

from src.modules.accounts.infrastructure.models import Company, User
from src.modules.projects.infrastructure.models import Project
from src.modules.trainings.infrastructure.models import Material, Training
from src.shared.infrastructure.models import BaseModel


# ═════════════════════════════════════════════════════════════
#  Artefactos del análisis
# ═════════════════════════════════════════════════════════════
class Transcript(BaseModel):
    material = models.OneToOneField(
        Material, on_delete=models.CASCADE, related_name="transcript"
    )
    language = models.CharField(max_length=10, default="es")
    full_text = models.TextField(blank=True)
    model = models.CharField(max_length=80, blank=True)
    confidence = models.FloatField(default=0)

    class Meta:
        db_table = "transcripts"
        verbose_name = _("transcripción")
        verbose_name_plural = _("transcripciones")

    def __str__(self) -> str:
        return f"Transcripción de {self.material_id}"


class TranscriptSegment(BaseModel):
    """Segmento con timestamps: la base de las citas 'video · minuto 14'."""

    transcript = models.ForeignKey(
        Transcript, on_delete=models.CASCADE, related_name="segments"
    )
    index = models.PositiveIntegerField()
    start_time = models.FloatField()
    end_time = models.FloatField()
    text = models.TextField()

    class Meta:
        db_table = "transcript_segments"
        ordering = ["index"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gte=models.F("start_time")),
                name="ck_segment_time_range",
            )
        ]
        indexes = [
            models.Index(fields=["transcript", "index"], name="idx_segment_transcript"),
            models.Index(fields=["transcript", "start_time"], name="idx_segment_start"),
        ]


class Chapter(BaseModel):
    """Tramo temático detectado por el LLM."""

    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="chapters")
    order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=250)
    summary = models.TextField(blank=True)
    start_time = models.FloatField(null=True, blank=True)
    end_time = models.FloatField(null=True, blank=True)
    start_page = models.PositiveIntegerField(null=True, blank=True)
    end_page = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "chapters"
        ordering = ["order"]
        verbose_name = _("capítulo")
        verbose_name_plural = _("capítulos")
        indexes = [models.Index(fields=["material", "order"], name="idx_chapter_material")]

    def __str__(self) -> str:
        return self.title


class Concept(BaseModel):
    """Concepto clave con su definición y ubicación en el material."""

    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="concepts")
    name = models.CharField(max_length=200)
    definition = models.TextField()
    relevance = models.FloatField(default=0.5)
    first_mention_time = models.FloatField(null=True, blank=True)
    page = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "concepts"
        ordering = ["-relevance", "name"]
        verbose_name = _("concepto")
        verbose_name_plural = _("conceptos")
        indexes = [models.Index(fields=["material", "-relevance"], name="idx_concept_material")]

    def __str__(self) -> str:
        return self.name


class Faq(BaseModel):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="faqs")
    question = models.TextField()
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "faqs"
        ordering = ["order"]
        verbose_name = _("pregunta frecuente")
        verbose_name_plural = _("preguntas frecuentes")


# ═════════════════════════════════════════════════════════════
#  RAG
# ═════════════════════════════════════════════════════════════
class Chunk(BaseModel):
    """
    Fragmento indexable · **fuente de verdad del RAG**.

    El índice FAISS es un derivado reconstruible; estos registros no (RN-10).
    """

    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="chunks")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="chunks")
    training = models.ForeignKey(
        Training, on_delete=models.CASCADE, related_name="chunks", null=True, blank=True
    )
    chapter = models.ForeignKey(
        Chapter, on_delete=models.SET_NULL, null=True, blank=True, related_name="chunks"
    )

    index = models.PositiveIntegerField()
    content = models.TextField()
    token_count = models.PositiveIntegerField(default=0)

    start_time = models.FloatField(null=True, blank=True)
    end_time = models.FloatField(null=True, blank=True)
    page = models.PositiveIntegerField(null=True, blank=True)
    heading = models.CharField(max_length=250, blank=True)

    embedded = models.BooleanField(default=False, db_index=True)
    embedding_model = models.CharField(max_length=120, blank=True)
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        db_table = "chunks"
        ordering = ["material", "index"]
        verbose_name = _("fragmento")
        verbose_name_plural = _("fragmentos")
        constraints = [
            models.UniqueConstraint(fields=["material", "index"], name="uq_chunk_material_index")
        ]
        indexes = [
            models.Index(fields=["project"], name="idx_chunk_project"),
            models.Index(fields=["training"], name="idx_chunk_training"),
            models.Index(fields=["project", "embedded"], name="idx_chunk_pending_embedding"),
            GinIndex(fields=["search_vector"], name="idx_chunk_search_vector"),
        ]

    def __str__(self) -> str:
        return f"{self.material_id}#{self.index}"

    def as_metadata(self) -> dict:
        """Metadatos que acompañan al vector en FAISS."""
        return {
            "chunk_id": str(self.id),
            "material_id": str(self.material_id),
            "training_id": str(self.training_id) if self.training_id else "",
            "project_id": str(self.project_id),
            "index": self.index,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "page": self.page,
            "heading": self.heading,
        }


# ═════════════════════════════════════════════════════════════
#  Chat y agente
# ═════════════════════════════════════════════════════════════
class ChatSession(BaseModel):
    training = models.ForeignKey(
        Training, on_delete=models.CASCADE, related_name="chat_sessions"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=200, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chat_sessions"
        ordering = ["-last_message_at", "-created_at"]
        verbose_name = _("conversación")
        verbose_name_plural = _("conversaciones")
        indexes = [
            models.Index(
                fields=["user", "training", "-last_message_at"], name="idx_chat_session_user"
            )
        ]

    def __str__(self) -> str:
        return self.title or f"Conversación {self.id}"


class ChatMessage(BaseModel):
    class Role(models.TextChoices):
        USER = "USER", _("Usuario")
        ASSISTANT = "ASSISTANT", _("Asistente")
        SYSTEM = "SYSTEM", _("Sistema")
        TOOL = "TOOL", _("Herramienta")

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()
    grounded = models.BooleanField(
        default=True, help_text=_("False cuando la IA no encontró contexto suficiente.")
    )
    needs_review = models.BooleanField(default=False)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    model = models.CharField(max_length=120, blank=True)
    feedback = models.SmallIntegerField(
        null=True, blank=True, help_text=_("1 útil, -1 no útil.")
    )

    class Meta:
        db_table = "chat_messages"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"], name="idx_chat_message_session")
        ]


class MessageCitation(BaseModel):
    """Cita verificada: siempre apunta a un chunk realmente recuperado."""

    message = models.ForeignKey(
        ChatMessage, on_delete=models.CASCADE, related_name="citations"
    )
    chunk = models.ForeignKey(
        Chunk, on_delete=models.SET_NULL, null=True, blank=True, related_name="citations"
    )
    material = models.ForeignKey(
        Material, on_delete=models.SET_NULL, null=True, blank=True, related_name="citations"
    )
    label = models.CharField(max_length=250)
    start_time = models.FloatField(null=True, blank=True)
    page = models.PositiveIntegerField(null=True, blank=True)
    score = models.FloatField(default=0)

    class Meta:
        db_table = "message_citations"
        ordering = ["-score"]


# ═════════════════════════════════════════════════════════════
#  Consumo de IA
# ═════════════════════════════════════════════════════════════
class AIUsageLog(BaseModel):
    """RF-051 · trazabilidad completa del consumo de IA."""

    class Purpose(models.TextChoices):
        TRANSCRIPTION = "TRANSCRIPTION", _("Transcripción")
        EMBEDDING = "EMBEDDING", _("Embeddings")
        ANALYSIS = "ANALYSIS", _("Análisis de material")
        CHAT = "CHAT", _("Chat RAG")
        AGENT = "AGENT", _("Agente tutor")
        EXAM_GENERATION = "EXAM_GENERATION", _("Generación de examen")
        EXAM_GRADING = "EXAM_GRADING", _("Corrección de examen")

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="ai_usage", null=True, blank=True
    )
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, related_name="ai_usage", null=True, blank=True
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name="ai_usage", null=True, blank=True
    )
    purpose = models.CharField(max_length=30, choices=Purpose.choices, db_index=True)
    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=120)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)

    class Meta:
        db_table = "ai_usage_logs"
        ordering = ["-created_at"]
        verbose_name = _("uso de IA")
        verbose_name_plural = _("usos de IA")
        indexes = [
            models.Index(fields=["company", "-created_at"], name="idx_ai_usage_company_date"),
            models.Index(fields=["project", "purpose"], name="idx_ai_usage_project"),
        ]

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
