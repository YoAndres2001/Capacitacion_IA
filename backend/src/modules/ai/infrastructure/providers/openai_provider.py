"""
Proveedor OpenAI · alternativa **opcional** de pago.

Existe únicamente para demostrar que el proveedor está desacoplado (RF-047):
cambiar `AI_PROVIDER=openai` sustituye la implementación sin tocar una sola
línea de dominio ni de casos de uso.
"""

from __future__ import annotations

import time
from typing import Any, Iterator

from django.conf import settings

from src.shared.domain.exceptions import AIProviderUnavailable
from src.shared.domain.value_object import TokenUsage

from ...application.ports.embeddings import EmbeddingsPort
from ...application.ports.llm import ChatMessage, LLMPort, LLMResponse
from .ollama import normalize, parse_json_loosely


def _client():
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise AIProviderUnavailable(
            "El paquete `openai` no está instalado. Use AI_PROVIDER=ollama (gratuito)."
        ) from exc

    config = settings.AI_SETTINGS["OPENAI"]
    if not config["API_KEY"]:
        raise AIProviderUnavailable(
            "Falta OPENAI_API_KEY. Use AI_PROVIDER=ollama para el modo gratuito."
        )
    return OpenAI(api_key=config["API_KEY"], base_url=config["BASE_URL"])


class OpenAILLM(LLMPort):
    def __init__(self, model: str | None = None) -> None:
        self._model = model or settings.AI_SETTINGS["OPENAI"]["LLM_MODEL"]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"

    def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        ai = settings.AI_SETTINGS
        started = time.monotonic()
        completion = _client().chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature if temperature is not None else ai["TEMPERATURE"],
            max_tokens=max_tokens or ai["MAX_TOKENS"],
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        usage = completion.usage

        return LLMResponse(
            content=completion.choices[0].message.content or "",
            usage=TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
                model=self._model,
                provider=self.provider_name,
                latency_ms=latency_ms,
            ),
        )

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        ai = settings.AI_SETTINGS
        stream = _client().chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature if temperature is not None else ai["TEMPERATURE"],
            max_tokens=max_tokens or ai["MAX_TOKENS"],
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def generate_json(
        self,
        messages: list[ChatMessage],
        *,
        schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[Any, TokenUsage]:
        started = time.monotonic()
        completion = _client().chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature if temperature is not None else 0.0,
            max_tokens=max_tokens or settings.AI_SETTINGS["MAX_TOKENS"],
            response_format={"type": "json_object"},
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        usage = completion.usage

        return (
            parse_json_loosely(completion.choices[0].message.content or ""),
            TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
                model=self._model,
                provider=self.provider_name,
                latency_ms=latency_ms,
            ),
        )

    def is_available(self) -> bool:
        try:
            _client().models.list()
            return True
        except Exception:
            return False


class OpenAIEmbeddings(EmbeddingsPort):
    #: dimensiones conocidas para evitar una llamada solo por saberlo
    KNOWN_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, model: str | None = None) -> None:
        self._model = model or settings.AI_SETTINGS["OPENAI"]["EMBEDDING_MODEL"]
        self._dimension = self.KNOWN_DIMENSIONS.get(self._model, 0)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def dimension(self) -> int:
        if not self._dimension:
            self._dimension = len(self.embed_query("dimensión"))
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = _client().embeddings.create(model=self._model, input=texts)
        return [normalize(item.embedding) for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
