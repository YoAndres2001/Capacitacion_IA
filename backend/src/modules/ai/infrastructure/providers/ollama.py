"""
Proveedor Ollama · LLM y embeddings **gratuitos**, ejecutados localmente.

Es la implementación por defecto: sin API key, sin costo y sin que el contenido
de la empresa salga de su infraestructura.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

import requests
from django.conf import settings
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.shared.domain.exceptions import AIProviderUnavailable
from src.shared.domain.value_object import TokenUsage
from src.shared.infrastructure.logging import get_logger

from ...application.ports.embeddings import EmbeddingsPort
from ...application.ports.llm import ChatMessage, LLMPort, LLMResponse

logger = get_logger("ai.ollama")

_RETRY = dict(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type((requests.RequestException,)),
    reraise=True,
)


def _config() -> dict[str, Any]:
    return settings.AI_SETTINGS["OLLAMA"]


#: Tamaños de ventana admitidos, de menor a mayor.
CONTEXT_BUCKETS = (2048, 4096, 8192, 16384)

#: Aproximación suficiente para español: ~4 caracteres por token.
CHARS_PER_TOKEN = 4


def fit_context(prompt_chars: int, max_output_tokens: int) -> int:
    """
    Elige la ventana de contexto más pequeña que acomode la conversación.

    En CPU el tamaño de `num_ctx` domina el rendimiento: medido en este
    proyecto, pasar de 8192 a 2048 multiplica la velocidad por 2–4 aunque el
    prompt sea el mismo, porque el coste de la atención y del caché KV crece con
    la ventana declarada, no con lo que realmente se usa.

    Por eso no se fija un valor grande "por si acaso": se calcula por llamada.
    """
    needed = prompt_chars // CHARS_PER_TOKEN + max_output_tokens
    needed = int(needed * 1.25) + 256  # margen para plantilla de chat y variación

    limit = int(settings.AI_SETTINGS["OLLAMA"].get("MAX_CTX", CONTEXT_BUCKETS[-1]))
    for bucket in CONTEXT_BUCKETS:
        if bucket >= needed:
            return min(bucket, limit)
    return limit


class OllamaLLM(LLMPort):
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        config = _config()
        self._model = model or config["LLM_MODEL"]
        self._base_url = (base_url or config["BASE_URL"]).rstrip("/")
        self._timeout = config["TIMEOUT"]

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "ollama"

    # ── Generación ───────────────────────────────────────────
    def generate(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        started = time.monotonic()
        payload = self._payload(messages, temperature, max_tokens, stream=False)

        data = self._post("/api/chat", payload)
        latency_ms = int((time.monotonic() - started) * 1000)

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            usage=TokenUsage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                model=self._model,
                provider=self.provider_name,
                latency_ms=latency_ms,
            ),
            raw=data,
        )

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        payload = self._payload(messages, temperature, max_tokens, stream=True)
        try:
            response = requests.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
                stream=True,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise AIProviderUnavailable(f"Ollama no responde: {exc}") from exc

        for line in response.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            token = data.get("message", {}).get("content", "")
            if token:
                yield token
            if data.get("done"):
                break

    def generate_json(
        self,
        messages: list[ChatMessage],
        *,
        schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[Any, TokenUsage]:
        """
        Fuerza el modo JSON nativo de Ollama.

        Con modelos pequeños es habitual que el texto venga envuelto en
        ```json ... ```; se limpia antes de parsear.
        """
        started = time.monotonic()
        payload = self._payload(
            messages,
            temperature if temperature is not None else 0.0,
            max_tokens,
            stream=False,
        )
        payload["format"] = schema if schema else "json"

        data = self._post("/api/chat", payload)
        latency_ms = int((time.monotonic() - started) * 1000)
        content = data.get("message", {}).get("content", "")

        usage = TokenUsage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            model=self._model,
            provider=self.provider_name,
            latency_ms=latency_ms,
        )
        return parse_json_loosely(content), usage

    def is_available(self) -> bool:
        try:
            response = requests.get(f"{self._base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    # ── Interno ──────────────────────────────────────────────
    def _payload(
        self,
        messages: list[ChatMessage],
        temperature: float | None,
        max_tokens: int | None,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        ai = settings.AI_SETTINGS
        predict = max_tokens or ai["MAX_TOKENS"]
        prompt_chars = sum(len(message.content) for message in messages)

        return {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "options": {
                "temperature": temperature if temperature is not None else ai["TEMPERATURE"],
                "num_predict": predict,
                "top_p": 0.9,
                "repeat_penalty": 1.05,
                "num_ctx": fit_context(prompt_chars, predict),
            },
        }

    @retry(**_RETRY)
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self._base_url}{path}", json=payload, timeout=self._timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            # Causa más común en equipos sin GPU: el modelo es demasiado grande.
            logger.warning(
                f"Ollama superó el tiempo límite de {self._timeout}s con el modelo "
                f"'{self._model}'. Considere un modelo menor (OLLAMA_LLM_MODEL) o "
                f"reducir AI_ANALYSIS_MAX_CHARS."
            )
            raise
        except requests.RequestException as exc:
            logger.warning(f"Fallo al llamar a Ollama ({path}): {exc}")
            raise


class OllamaEmbeddings(EmbeddingsPort):
    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        config = _config()
        self._model = model or config["EMBEDDING_MODEL"]
        self._base_url = (base_url or config["BASE_URL"]).rstrip("/")
        self._timeout = config["TIMEOUT"]
        self._dimension = 0

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def dimension(self) -> int:
        if not self._dimension:
            self._dimension = len(self.embed_query("dimensión"))
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._embed(texts)
        self._dimension = len(vectors[0]) if vectors else self._dimension
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed([text])
        return vectors[0] if vectors else []

    @retry(**_RETRY)
    def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = requests.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise AIProviderUnavailable(f"Ollama (embeddings) no responde: {exc}") from exc

        vectors = payload.get("embeddings") or []
        return [normalize(vector) for vector in vectors]


# ─────────────────────────────────────────────────────────────
#  Utilidades compartidas por los proveedores
# ─────────────────────────────────────────────────────────────
def normalize(vector: list[float]) -> list[float]:
    """Normalización L2: permite usar producto interno como similitud coseno."""
    magnitude = sum(component * component for component in vector) ** 0.5
    if magnitude == 0:
        return vector
    return [component / magnitude for component in vector]


def parse_json_loosely(content: str) -> Any:
    """
    Parsea JSON tolerando el ruido típico de los modelos pequeños.

    Quita vallas de código y recorta hasta el primer `{`/`[` y el último `}`/`]`.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]

    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"El modelo no devolvió JSON válido: {content[:300]}")
