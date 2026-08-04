"""
Máquina de estados del material (lógica de dominio pura).

Centraliza las transiciones legales descritas en docs/06-modelo-dominio.md §5.
No importa Django: es testeable sin base de datos.
"""

from __future__ import annotations

from enum import StrEnum

from src.shared.domain.exceptions import InvalidStateTransition


class MaterialStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    ANALYZING = "ANALYZING"
    AVAILABLE = "AVAILABLE"
    ERROR = "ERROR"


#: Transiciones permitidas. Cualquier otra combinación es un error de programación.
ALLOWED: dict[MaterialStatus, frozenset[MaterialStatus]] = {
    MaterialStatus.PENDING: frozenset({MaterialStatus.PROCESSING, MaterialStatus.ERROR}),
    MaterialStatus.PROCESSING: frozenset({MaterialStatus.ANALYZING, MaterialStatus.ERROR}),
    MaterialStatus.ANALYZING: frozenset({MaterialStatus.AVAILABLE, MaterialStatus.ERROR}),
    # Reproceso y reintento vuelven al inicio del pipeline.
    MaterialStatus.AVAILABLE: frozenset({MaterialStatus.PROCESSING}),
    MaterialStatus.ERROR: frozenset({MaterialStatus.PROCESSING, MaterialStatus.PENDING}),
}


class MaterialStateMachine:
    @staticmethod
    def can_transition(current: str, target: str) -> bool:
        try:
            return MaterialStatus(target) in ALLOWED[MaterialStatus(current)]
        except (KeyError, ValueError):
            return False

    @staticmethod
    def assert_transition(current: str, target: str) -> None:
        if not MaterialStateMachine.can_transition(current, target):
            raise InvalidStateTransition("Material", current, target)

    @staticmethod
    def is_queryable(status: str) -> bool:
        """RN-05: solo el material disponible alimenta el chat y los exámenes."""
        return status == MaterialStatus.AVAILABLE

    @staticmethod
    def is_in_progress(status: str) -> bool:
        return status in {
            MaterialStatus.PENDING,
            MaterialStatus.PROCESSING,
            MaterialStatus.ANALYZING,
        }

    @staticmethod
    def can_be_reprocessed(status: str) -> bool:
        return status in {MaterialStatus.AVAILABLE, MaterialStatus.ERROR}
