"""Eventos de dominio (ver docs/06-modelo-dominio.md §7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def name(self) -> str:
        return type(self).__name__

    def payload(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if key in {"event_id", "occurred_at"}:
                continue
            data[key] = str(value) if isinstance(value, (UUID, datetime)) else value
        return data


# ── Materiales ───────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class MaterialUploaded(DomainEvent):
    material_id: UUID
    lesson_id: UUID
    project_id: UUID
    material_type: str


@dataclass(frozen=True, kw_only=True)
class MaterialStatusChanged(DomainEvent):
    material_id: UUID
    status: str
    step: str = ""
    progress: int = 0
    error_code: str | None = None


@dataclass(frozen=True, kw_only=True)
class MaterialProcessed(DomainEvent):
    material_id: UUID
    project_id: UUID
    chunk_count: int
    partial: bool = False


# ── Contenido y aprendizaje ──────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class TrainingPublished(DomainEvent):
    training_id: UUID
    project_id: UUID


@dataclass(frozen=True, kw_only=True)
class UserEnrolled(DomainEvent):
    enrollment_id: UUID
    user_id: UUID
    training_id: UUID


@dataclass(frozen=True, kw_only=True)
class LessonCompleted(DomainEvent):
    enrollment_id: UUID
    lesson_id: UUID
    user_id: UUID


@dataclass(frozen=True, kw_only=True)
class TrainingCompleted(DomainEvent):
    enrollment_id: UUID
    user_id: UUID
    training_id: UUID


# ── Evaluación ───────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class AttemptGraded(DomainEvent):
    attempt_id: UUID
    user_id: UUID
    exam_id: UUID
    score: float
    passed: bool


# ── IA ───────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class AIQueryAnswered(DomainEvent):
    session_id: UUID
    message_id: UUID
    training_id: UUID
    grounded: bool
    citation_count: int


@dataclass(frozen=True, kw_only=True)
class AIAnsweredWithoutContext(DomainEvent):
    """Señal de brecha de contenido: la pregunta no tenía respuesta en el material."""

    training_id: UUID
    user_id: UUID
    question: str
