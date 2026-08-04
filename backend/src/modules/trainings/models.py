"""Reexporta los modelos ORM del módulo Trainings para el registro de Django."""

from .infrastructure.models import (  # noqa: F401
    Enrollment,
    Lesson,
    LessonProgress,
    Material,
    Module,
    Note,
    ProcessingJob,
    Training,
    UploadSession,
)

__all__ = [
    "Enrollment",
    "Lesson",
    "LessonProgress",
    "Material",
    "Module",
    "Note",
    "ProcessingJob",
    "Training",
    "UploadSession",
]
