"""Registro del consumo de IA (RF-051) y estimación de costo."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from src.shared.domain.value_object import TokenUsage
from src.shared.infrastructure.logging import get_logger

logger = get_logger("ai.usage")

#: Precio por 1.000 tokens (USD) de los modelos de Groq, único proveedor con
#: costo. El nivel gratuito no cobra; estos son los precios del de pago.
#: Un modelo ausente se contabiliza como 0: la cifra es una estimación para el
#: panel de consumo, no una factura.
PRICING: dict[str, tuple[Decimal, Decimal]] = {
    "llama-3.3-70b-versatile": (Decimal("0.00059"), Decimal("0.00079")),
    "llama-3.1-8b-instant": (Decimal("0.00005"), Decimal("0.00008")),
    "openai/gpt-oss-120b": (Decimal("0.00015"), Decimal("0.00075")),
    "openai/gpt-oss-20b": (Decimal("0.0001"), Decimal("0.0005")),
}


def estimate_cost(usage: TokenUsage) -> Decimal:
    # Los embeddings se calculan dentro del worker: no tienen costo por token.
    if usage.provider == "local":
        return Decimal("0")
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
