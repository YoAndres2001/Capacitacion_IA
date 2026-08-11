"""
Puerto del modelo de lenguaje (RF-047).

El dominio y los casos de uso solo conocen este contrato; la implementación
productiva es `GroqLLM`, el único proveedor externo de la plataforma. El puerto
se mantiene porque es lo que permite probar el pipeline con dobles sin llamar a
la API real.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator

from src.shared.domain.value_object import TokenUsage


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMResponse:
    content: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw: dict[str, Any] = field(default_factory=dict)


class LLMPort(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generación completa (bloqueante)."""

    @abstractmethod
    def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Generación token a token, para el chat en vivo (RF-049)."""

    @abstractmethod
    def generate_json(
        self,
        messages: list[ChatMessage],
        *,
        schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[Any, TokenUsage]:
        """
        Salida estructurada.

        Con `schema` se pide Structured Outputs (JSON Schema estricto) cuando el
        modelo lo admite; si no, se cae a modo JSON y el llamador valida con
        Pydantic y reintenta de forma correctiva.

        Acotar `max_tokens` es la palanca más directa sobre la latencia y sobre
        la cuota por minuto de Groq, que descuenta el máximo declarado aunque no
        se llegue a usar.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Comprobación de salud del proveedor."""
