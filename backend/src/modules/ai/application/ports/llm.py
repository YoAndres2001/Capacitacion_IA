"""
Puerto del modelo de lenguaje (RF-047).

Cualquier proveedor (Ollama local gratuito, OpenAI, otro) implementa esta
interfaz. El dominio y los casos de uso solo conocen este contrato.
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

        Indispensable con modelos locales pequeños: el proveedor fuerza el modo
        JSON y el llamador valida con Pydantic.

        `max_tokens` importa más de lo que parece en CPU: el tiempo de respuesta
        es casi proporcional a los tokens generados, así que acotar la salida es
        la palanca más directa para que el análisis termine en minutos.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Comprobación de salud del proveedor."""
