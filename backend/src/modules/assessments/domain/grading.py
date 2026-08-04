"""
Corrección determinística (dominio puro).

Las preguntas cerradas y de respuesta corta se corrigen aquí, sin LLM: es
exacto, instantáneo y gratuito. Solo las abiertas necesitan el modelo.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
    "y", "o", "que", "en", "a", "por", "para", "con", "se", "su", "es", "son",
}


@dataclass(frozen=True)
class GradeResult:
    is_correct: bool
    points: Decimal
    feedback: str = ""
    partial: bool = False


def normalize(text: str) -> str:
    """Minúsculas, sin acentos ni puntuación: comparación tolerante pero determinista."""
    lowered = text.strip().lower()
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", lowered)
        if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9\s]", " ", without_accents).strip()


def tokens(text: str) -> set[str]:
    return {word for word in normalize(text).split() if word and word not in STOPWORDS}


class AnswerMatcher:
    """Estrategias de corrección por tipo de pregunta."""

    @staticmethod
    def grade_single_choice(
        selected: list[str], correct: list[str], points: Decimal
    ) -> GradeResult:
        is_correct = len(selected) == 1 and set(selected) == set(correct)
        return GradeResult(
            is_correct=is_correct,
            points=points if is_correct else Decimal("0"),
            feedback="" if is_correct else "La alternativa seleccionada no es la correcta.",
        )

    @staticmethod
    def grade_multiple_choice(
        selected: list[str], correct: list[str], points: Decimal, *, allow_partial: bool = True
    ) -> GradeResult:
        """
        Puntaje parcial con penalización por selección incorrecta.

        Marcar todas las opciones no debe dar puntaje completo: se descuentan
        los falsos positivos.
        """
        selected_set, correct_set = set(selected), set(correct)
        if selected_set == correct_set:
            return GradeResult(True, points)

        if not allow_partial or not correct_set:
            return GradeResult(False, Decimal("0"), "La combinación seleccionada no es correcta.")

        hits = len(selected_set & correct_set)
        misses = len(selected_set - correct_set)
        ratio = max(0.0, (hits - misses) / len(correct_set))
        awarded = (points * Decimal(str(round(ratio, 4)))).quantize(Decimal("0.01"))

        return GradeResult(
            is_correct=False,
            points=awarded,
            feedback=f"Acertó {hits} de {len(correct_set)} opciones correctas.",
            partial=awarded > 0,
        )

    @staticmethod
    def grade_short_answer(
        answer: str, expected: str, points: Decimal, *, threshold: float = 0.7
    ) -> GradeResult:
        """
        Coincidencia normalizada + solapamiento de términos significativos.

        Devuelve `partial=True` cuando queda en zona gris; ahí el llamador puede
        escalar a verificación semántica con el LLM.
        """
        if not answer.strip():
            return GradeResult(False, Decimal("0"), "Sin respuesta.")

        normalized_answer, normalized_expected = normalize(answer), normalize(expected)
        if normalized_answer == normalized_expected:
            return GradeResult(True, points)

        expected_tokens = tokens(expected)
        if not expected_tokens:
            return GradeResult(False, Decimal("0"), partial=True)

        overlap = len(tokens(answer) & expected_tokens) / len(expected_tokens)
        if overlap >= threshold:
            return GradeResult(True, points, "Respuesta equivalente a la esperada.")
        if overlap >= 0.4:
            return GradeResult(
                False,
                Decimal("0"),
                "La respuesta contiene parte de los elementos esperados.",
                partial=True,
            )
        return GradeResult(False, Decimal("0"), "La respuesta no coincide con la esperada.")


class ScoringService:
    """Agregación del puntaje del intento y política de nota final."""

    @staticmethod
    def total(results: list[GradeResult]) -> Decimal:
        return sum((result.points for result in results), Decimal("0"))

    @staticmethod
    def final_score(scores: list[Decimal], policy: str) -> Decimal:
        if not scores:
            return Decimal("0")
        if policy == "LAST":
            return scores[-1]
        if policy == "AVERAGE":
            return (sum(scores, Decimal("0")) / len(scores)).quantize(Decimal("0.01"))
        return max(scores)
