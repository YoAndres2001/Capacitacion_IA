"""Servicio de dominio: cálculo de progreso de una capacitación (RF-034)."""

from __future__ import annotations

from dataclasses import dataclass

COMPLETION_THRESHOLD = 0.9  # 90 % de reproducción marca la lección como completada (RF-033)


@dataclass(frozen=True)
class LessonProgressSnapshot:
    lesson_id: str
    is_mandatory: bool
    completed: bool
    watched_seconds: int
    duration_seconds: int

    @property
    def ratio(self) -> float:
        if self.duration_seconds <= 0:
            return 1.0 if self.completed else 0.0
        return min(self.watched_seconds / self.duration_seconds, 1.0)


class ProgressCalculator:
    """
    El avance se calcula sobre las lecciones OBLIGATORIAS.

    Si no hay lecciones obligatorias, se consideran todas: así una capacitación
    sin marcar obligatoriedad sigue midiendo progreso de forma razonable.
    """

    @staticmethod
    def compute(snapshots: list[LessonProgressSnapshot]) -> float:
        if not snapshots:
            return 0.0

        relevant = [s for s in snapshots if s.is_mandatory] or snapshots
        completed = sum(1 for s in relevant if s.completed)
        return round(completed / len(relevant) * 100, 2)

    @staticmethod
    def should_complete_lesson(watched_seconds: int, duration_seconds: int) -> bool:
        if duration_seconds <= 0:
            return watched_seconds > 0
        return watched_seconds / duration_seconds >= COMPLETION_THRESHOLD

    @staticmethod
    def can_take_exam(progress: float, min_progress_required: int) -> bool:
        """RN-07."""
        return progress >= min_progress_required
