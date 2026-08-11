"""
Proveedor Groq · el ÚNICO LLM de la plataforma.

Resuelve chat y tutor, análisis de material (resumen, conceptos, capítulos,
FAQ), generación y corrección de exámenes, y la respuesta final del RAG.

Los embeddings NO vienen de aquí: Groq no ofrece `/embeddings` (responde 404) y
se calculan en local con SentenceTransformers (ver
`sentence_transformers_provider`), de modo que Groq sigue siendo el único
servicio externo al que se hacen llamadas.

La credencial, los reintentos y la traducción de errores viven en `groq_http`,
compartidos con el adaptador de transcripción.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

import requests
from django.conf import settings
from tenacity import retry

from src.shared.domain.exceptions import AIProviderUnavailable
from src.shared.domain.value_object import TokenUsage
from src.shared.infrastructure.logging import get_logger

from ...application.ports.llm import ChatMessage, LLMPort, LLMResponse
from .groq_http import auth_headers, config, raise_for_status, retry_policy
from .parsing import parse_json_loosely

logger = get_logger("ai.groq")

_RETRY = retry_policy()

#: Se descubre en la primera llamada rechazada y evita repetir el aviso.
_STRUCTURED_OUTPUTS_UNSUPPORTED = False


class GroqLLM(LLMPort):
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        settings_groq = config()
        self._model = model or settings_groq["LLM_MODEL"]
        self._base_url = (base_url or settings_groq["BASE_URL"]).rstrip("/")
        self._timeout = settings_groq["TIMEOUT"]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "groq"

    # ── Generación ───────────────────────────────────────────
    def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        started = time.monotonic()
        data = self._post(self._payload(messages, temperature, max_tokens))
        latency_ms = int((time.monotonic() - started) * 1000)

        return LLMResponse(
            content=self._first_content(data),
            usage=self._usage(data, latency_ms),
            raw=data,
        )

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        payload = self._payload(messages, temperature, max_tokens)
        payload["stream"] = True
        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
                stream=True,
            )
            raise_for_status(response)
        except requests.RequestException as exc:
            raise AIProviderUnavailable(f"Groq no responde: {exc}") from exc

        # Server-Sent Events: cada evento llega como `data: {...}` y el flujo
        # termina con el centinela `data: [DONE]`.
        #
        # Se decodifica a mano en vez de usar `decode_unicode=True`: en un
        # `text/event-stream` sin charset explícito, requests cae a ISO-8859-1 y
        # los acentos llegan como "cÃ³mo".
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace")
            if not line.startswith("data:"):
                continue
            chunk = line[len("data:") :].strip()
            if chunk == "[DONE]":
                break
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            choices = data.get("choices") or [{}]
            token = (choices[0].get("delta") or {}).get("content") or ""
            if token:
                yield token

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

        Con un esquema se intenta primero `json_schema` estricto (Structured
        Outputs), que garantiza la forma y no solo la sintaxis. Los modelos que
        no lo soportan responden 400: en ese caso se cae a `json_object` (modo
        JSON) y la forma la valida el llamador con Pydantic, que además reintenta
        de forma correctiva.
        """
        temperature = temperature if temperature is not None else 0.0
        started = time.monotonic()

        if schema is not None and not _STRUCTURED_OUTPUTS_UNSUPPORTED:
            data = self._post_structured(messages, schema, temperature, max_tokens)
        else:
            payload = self._payload(_ensure_json_instruction(messages), temperature, max_tokens)
            payload["response_format"] = {"type": "json_object"}
            data = self._post(payload)

        latency_ms = int((time.monotonic() - started) * 1000)
        return parse_json_loosely(self._first_content(data)), self._usage(data, latency_ms)

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self._base_url}/models", headers=self._headers(), timeout=10)
            return response.status_code == 200
        except (requests.RequestException, AIProviderUnavailable):
            return False

    # ── Interno ──────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        return {**auth_headers(), "Content-Type": "application/json"}

    def _payload(
        self,
        messages: list[ChatMessage],
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        ai = settings.AI_SETTINGS
        return {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature if temperature is not None else ai["TEMPERATURE"],
            "max_tokens": max_tokens or ai["MAX_TOKENS"],
            "top_p": 0.9,
            "stream": False,
        }

    def _post_structured(
        self,
        messages: list[ChatMessage],
        schema: dict[str, Any],
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        """
        Structured Outputs con degradación a modo JSON.

        No todos los modelos del catálogo de Groq aceptan `json_schema`, y el
        modelo es configurable por entorno: si el que está en uso lo rechaza, la
        llamada no debe perderse.

        El rechazo se recuerda para todo el proceso: es una propiedad del modelo,
        no de la petición, y sin esa memoria cada cadena de análisis gastaría una
        petición fallida —y su parte de la cuota por minuto— antes de degradarse.

        Nótese que el esquema NO se copia al prompt: en el intento estricto lo
        valida Groq, y en la degradación el prompt del llamador ya describe el
        formato. Incrustarlo dispararía el consumo de tokens justo donde el nivel
        gratuito es más estrecho.
        """
        payload = self._payload(messages, temperature, max_tokens)
        strict = {
            **payload,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "respuesta", "schema": schema, "strict": True},
            },
        }
        try:
            return self._post(strict)
        except (AIProviderUnavailable, requests.HTTPError) as exc:
            global _STRUCTURED_OUTPUTS_UNSUPPORTED
            _STRUCTURED_OUTPUTS_UNSUPPORTED = True
            logger.info(
                f"El modelo '{self._model}' no admite Structured Outputs "
                f"({str(exc)[:200]}); se usa modo JSON + validación Pydantic."
            )
            fallback = self._payload(_ensure_json_instruction(messages), temperature, max_tokens)
            fallback["response_format"] = {"type": "json_object"}
            return self._post(fallback)

    @staticmethod
    def _first_content(data: dict[str, Any]) -> str:
        choices = data.get("choices") or [{}]
        return (choices[0].get("message") or {}).get("content") or ""

    def _usage(self, data: dict[str, Any], latency_ms: int) -> TokenUsage:
        usage = data.get("usage") or {}
        return TokenUsage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            model=data.get("model") or self._model,
            provider=self.provider_name,
            latency_ms=latency_ms,
        )

    @retry(**_RETRY)
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            )
            raise_for_status(response)
            return response.json()
        except requests.RequestException as exc:
            logger.warning(f"Fallo al llamar a Groq: {exc}")
            raise


def _ensure_json_instruction(messages: list[ChatMessage]) -> list[ChatMessage]:
    """
    El modo JSON de Groq exige que el prompt mencione JSON; sin eso devuelve 400.

    La mayoría de los prompts del proyecto ya lo hacen, pero garantizarlo aquí
    evita que añadir una cadena nueva rompa la llamada.
    """
    if any("json" in message.content.lower() for message in messages):
        return messages

    return [
        *messages,
        ChatMessage(
            role="system",
            content="Responde ÚNICAMENTE con JSON válido, sin texto ni explicaciones.",
        ),
    ]
