"""
Cliente HTTP común de Groq · credencial, reintentos y traducción de errores.

Lo comparten el adaptador de LLM (`groq_provider`) y el de transcripción
(`transcription.groq_whisper`): ambos hablan con la misma API, con la misma
cuota y con los mismos modos de fallo, así que la política de reintentos vive en
un solo sitio.

Se habla HTTP directo con `requests` en lugar de usar un SDK: es una dependencia
que el proyecto ya tenía y mantiene el arranque libre de paquetes opcionales.

**La API key se lee siempre de `settings`, que a su vez la toma de la variable de
entorno `GROQ_API_KEY`. Nunca se escribe en código ni se registra en los logs.**
"""

from __future__ import annotations

import re
from typing import Any

import requests
from django.conf import settings
from tenacity import retry_if_exception_type, stop_after_attempt, wait_exponential

from src.shared.domain.exceptions import AIProviderUnavailable
from src.shared.infrastructure.logging import get_logger

logger = get_logger("ai.groq")

#: Techo de espera ante un 429. La cuota de tokens de Groq se repone cada minuto,
#: así que esperar algo más de eso cubre el peor caso sin colgar la tarea.
MAX_RATE_LIMIT_WAIT = 70.0


class RateLimited(requests.RequestException):
    """429 de Groq, con el tiempo que la propia API pide esperar."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def config() -> dict[str, Any]:
    return settings.AI_SETTINGS["GROQ"]


def require_api_key() -> str:
    """
    Devuelve la credencial o falla con un mensaje accionable.

    Groq es el único proveedor externo del sistema: sin esta clave no hay chat,
    ni análisis, ni exámenes, ni transcripción.
    """
    api_key = config()["API_KEY"]
    if not api_key:
        raise AIProviderUnavailable(
            "Falta GROQ_API_KEY. Es obligatoria: Groq es el único proveedor de IA "
            "de la plataforma. Obtenga una clave en https://console.groq.com/keys "
            "y defínala como variable de entorno GROQ_API_KEY."
        )
    return api_key


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {require_api_key()}"}


def retry_wait(retry_state) -> float:
    """
    Ante un límite de uso, espera lo que Groq indica en vez de adivinar.

    El nivel gratuito responde 429 con el tiempo exacto de reposición. Una curva
    exponencial acotada a 15 s se rendía antes de que la cuota volviera, y la
    generación de un examen moría a medias.
    """
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exception, RateLimited):
        return min(exception.retry_after, MAX_RATE_LIMIT_WAIT)
    return wait_exponential(multiplier=1, min=2, max=15)(retry_state)


def retry_policy(attempts: int = 4) -> dict[str, Any]:
    """Política de `tenacity` compartida: backoff exponencial + respeto del 429."""
    return {
        "stop": stop_after_attempt(attempts),
        "wait": retry_wait,
        "retry": retry_if_exception_type((requests.RequestException,)),
        "reraise": True,
    }


def raise_for_status(response: requests.Response) -> None:
    """
    Traduce el error de Groq a algo accionable.

    Un 429 es lo habitual en el nivel gratuito (límite de peticiones o de tokens
    por minuto) y sí conviene reintentarlo; un 401 o un 400 por modelo
    inexistente no mejoran reintentando, así que se cortan de inmediato. Un 5xx
    sale como `HTTPError` y la política de reintentos lo recoge.

    El detalle que se registra viene del cuerpo de la respuesta: nunca incluye la
    cabecera `Authorization` ni la clave.
    """
    if response.status_code < 400:
        return

    try:
        detail = (response.json().get("error") or {}).get("message") or response.text
    except ValueError:
        detail = response.text

    if response.status_code in (401, 403):
        raise AIProviderUnavailable(f"Groq rechazó la credencial: {detail}")
    if response.status_code == 404 or _is_unknown_model(detail):
        raise AIProviderUnavailable(
            f"Groq no reconoce el modelo configurado: {detail}. "
            f"Revise GROQ_LLM_MODEL / GROQ_WHISPER_MODEL contra "
            f"https://console.groq.com/docs/models"
        )
    if response.status_code == 429:
        delay = retry_after(response, detail)
        logger.warning(f"Groq aplicó límite de uso; se reintentará en {delay:.0f} s: {detail}")
        raise RateLimited(f"429 de Groq: {detail}", delay)

    # El resto de los 4xx (petición mal formada, formato de salida no admitido,
    # audio ilegible…) no mejoran reintentando: se cortan como error de
    # proveedor, que NO es un `RequestException` y por tanto tenacity no repite.
    # Solo 408 —tiempo agotado en el servidor— y los 5xx entran al backoff.
    if 400 <= response.status_code < 500 and response.status_code != 408:
        raise AIProviderUnavailable(f"Groq rechazó la petición ({response.status_code}): {detail}")

    response.raise_for_status()


#: Frases con las que Groq indica que el modelo no existe o fue retirado.
#: Buscar solo la palabra "model" no vale: el 400 de "this model does not
#: support response format `json_schema`" también la lleva, y mandaba a cambiar
#: GROQ_LLM_MODEL cuando el modelo es correcto y solo le falta esa capacidad.
_UNKNOWN_MODEL_PHRASES = (
    "does not exist",
    "not found",
    "no such model",
    "decommissioned",
    "has been deprecated",
    "unknown model",
)


def _is_unknown_model(detail: str) -> bool:
    lowered = detail.lower()
    return "model" in lowered and any(phrase in lowered for phrase in _UNKNOWN_MODEL_PHRASES)


def retry_after(response: requests.Response, detail: str) -> float:
    """
    Cuánto esperar tras un 429, según lo que diga la propia respuesta.

    Groq lo publica de tres formas y no siempre están las tres: la cabecera
    `retry-after`, la de reposición de tokens (`4m19.2s`, `29.055s`) y el propio
    mensaje ("Please try again in 7.5s"). Se toma la primera disponible.
    """
    header = response.headers.get("retry-after")
    if header:
        try:
            return max(1.0, float(header))
        except ValueError:
            pass

    reset = response.headers.get("x-ratelimit-reset-tokens") or response.headers.get(
        "x-ratelimit-reset-requests"
    )
    if reset:
        seconds = parse_duration(reset)
        if seconds:
            return seconds + 1.0

    match = re.search(r"try again in ([\d.]+)\s*s", detail, re.IGNORECASE)
    if match:
        return float(match.group(1)) + 1.0

    return 20.0


def parse_duration(value: str) -> float:
    """Convierte los formatos de Groq (`29.055s`, `4m19.2s`, `1h2m3s`) a segundos."""
    total = 0.0
    found = False
    for amount, unit in re.findall(r"([\d.]+)\s*(h|m|s|ms)", value):
        found = True
        total += float(amount) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unit]
    return total if found else 0.0
