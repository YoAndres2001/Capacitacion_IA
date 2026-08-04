"""Value Objects transversales del dominio (inmutables y autovalidados)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .exceptions import ValidationError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not EMAIL_RE.match(normalized):
            raise ValidationError(f"Correo electrónico inválido: '{self.value}'.")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value

    @property
    def domain(self) -> str:
        return self.value.split("@", 1)[1]


@dataclass(frozen=True, slots=True)
class Slug:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().lower()
        if not (2 <= len(v) <= 60) or not SLUG_RE.match(v):
            raise ValidationError(
                f"Slug inválido: '{self.value}'. Use minúsculas, números y guiones (2-60)."
            )
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Rango temporal en segundos dentro de un material de video/audio."""

    start: float
    end: float

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValidationError("El inicio del rango no puede ser negativo.")
        if self.end < self.start:
            raise ValidationError("El fin del rango no puede ser anterior al inicio.")

    @property
    def duration(self) -> float:
        return self.end - self.start

    def contains(self, second: float) -> bool:
        return self.start <= second <= self.end

    def overlaps(self, other: TimeRange) -> bool:
        return self.start < other.end and other.start < self.end

    def as_label(self) -> str:
        return f"{_hhmmss(self.start)}–{_hhmmss(self.end)}"


def _hhmmss(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


@dataclass(frozen=True, slots=True)
class Score:
    """Puntaje de 0 a 100 con dos decimales."""

    value: Decimal

    def __post_init__(self) -> None:
        try:
            v = Decimal(self.value).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError) as exc:
            raise ValidationError("Puntaje inválido.") from exc
        if not (Decimal("0") <= v <= Decimal("100")):
            raise ValidationError("El puntaje debe estar entre 0 y 100.")
        object.__setattr__(self, "value", v)

    @classmethod
    def from_points(cls, obtained: float, total: float) -> Score:
        if total <= 0:
            return cls(Decimal("0"))
        return cls(Decimal(str(obtained / total * 100)))

    def passes(self, minimum: int) -> bool:
        return self.value >= Decimal(minimum)

    def __float__(self) -> float:
        return float(self.value)


@dataclass(frozen=True, slots=True)
class Percentage:
    value: float

    def __post_init__(self) -> None:
        if not (0 <= self.value <= 100):
            raise ValidationError("El porcentaje debe estar entre 0 y 100.")
        object.__setattr__(self, "value", round(float(self.value), 2))

    def __float__(self) -> float:
        return self.value


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Consumo de un proveedor de IA, para auditoría y control de costos."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    provider: str = ""
    latency_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            model=self.model or other.model,
            provider=self.provider or other.provider,
            latency_ms=self.latency_ms + other.latency_ms,
        )
