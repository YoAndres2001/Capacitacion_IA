"""Registro del consumo de IA (RF-051) y estimación de costo."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from src.shared.domain.value_object import TokenUsage
from src.shared.infrastructure.logging import get_logger

logger = get_logger("ai.usage")

#: Precio por 1.000 tokens (USD). Ollama es local: costo cero.
PRICING: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.00015"), Decimal("0.0006")),
    "gpt-4o": (Decimal("0.0025"), Decimal("0.01")),
    "text-embedding-3-small": (Decimal("0.00002"), Decimal("0")),
    "text-embedding-3-large": (Decimal("0.00013"), Decimal("0")),
}


def estimate_cost(usage: TokenUsage) -> Decimal:
    if usage.provider == "ollama":
        return Decimal("0")  # modelo local: gratuito
    prompt_price, completion_price = PRICING.get(usage.model, (Decimal("0"), Decimal("0")))
    return (
        Decimal(usage.prompt_tokens) / 1000 * prompt_price
        + Decimal(usage.completion_tokens) / 1000 * completion_price
    ).quantize(Decimal("0.000001"))


def record_usage(
    *,
    usage: TokenUsage,
    purpose: str,
    company_id: UUID | None = None,
    project_id: UUID | None = None,
    user_id: UUID | None = None,
    success: bool = True,
    error: str = "",
) -> None:
    """El registro de consumo nunca debe romper el flujo de negocio."""
    from .models import AIUsageLog

    try:
        AIUsageLog.objects.create(
            company_id=company_id,
            project_id=project_id,
            user_id=user_id,
            purpose=purpose,
            provider=usage.provider or "unknown",
            model=usage.model or "unknown",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=estimate_cost(usage),
            latency_ms=usage.latency_ms,
            success=success,
            error=error[:1000],
        )
    except Exception:  # pragma: no cover
        logger.warning("No se pudo registrar el consumo de IA", exc_info=True)
