"""
Detalles del proveedor Groq que no se ven hasta que fallan en producción.

Dos cosas rompen de forma silenciosa al hablar con su API: pedir modo JSON sin
que el prompt mencione JSON (la API responde 400) y confundir un límite de uso
—reintentable— con una credencial inválida —que no lo es—.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from src.modules.ai.application.ports.llm import ChatMessage
from src.modules.ai.infrastructure.providers.groq_http import (
    MAX_RATE_LIMIT_WAIT,
    RateLimited,
    raise_for_status,
    retry_after,
    retry_wait,
)
from src.modules.ai.infrastructure.providers.groq_provider import _ensure_json_instruction
from src.shared.domain.exceptions import AIProviderUnavailable

pytestmark = pytest.mark.unit


class _Response:
    """Lo mínimo de `requests.Response` que mira `_raise_for_status`."""

    def __init__(self, status_code: int, message: str = "", headers: dict | None = None) -> None:
        self.status_code = status_code
        self._message = message
        self.text = message
        self.headers = headers or {}

    def json(self) -> dict:
        return {"error": {"message": self._message}}

    def raise_for_status(self) -> None:
        raise requests.HTTPError(f"{self.status_code}: {self._message}")


# ── Modo JSON ────────────────────────────────────────────────
def test_no_toca_el_prompt_si_ya_menciona_json():
    messages = [ChatMessage(role="system", content="Devuelves SIEMPRE JSON válido.")]
    assert _ensure_json_instruction(messages) is messages


def test_anade_la_instruccion_cuando_el_prompt_no_menciona_json():
    messages = [ChatMessage(role="user", content="Resume el material en dos capítulos.")]

    prepared = _ensure_json_instruction(messages)

    assert len(prepared) == len(messages) + 1
    assert "JSON" in prepared[-1].content
    assert prepared[0] is messages[0]  # el prompt original no se altera


# ── Traducción de errores ────────────────────────────────────
def test_una_credencial_rechazada_no_se_reintenta():
    """401 es definitivo: se corta con un mensaje accionable, no con un HTTPError."""
    with pytest.raises(AIProviderUnavailable, match="credencial"):
        raise_for_status(_Response(401, "Invalid API Key"))


def test_un_modelo_inexistente_no_se_reintenta():
    with pytest.raises(AIProviderUnavailable, match="modelo"):
        raise_for_status(_Response(404, "The model `llama-x` does not exist"))


def test_un_limite_de_uso_si_se_reintenta():
    """429 sale como RateLimited para que tenacity vuelva a intentarlo."""
    with pytest.raises(RateLimited):
        raise_for_status(_Response(429, "Rate limit reached"))


def test_un_formato_no_admitido_no_se_confunde_con_un_modelo_inexistente():
    """
    Medido contra la API real: `llama-3.3-70b-versatile` no admite `json_schema`
    y responde 400 con "This model does not support response format...".

    El mensaje lleva la palabra "model", pero el modelo es correcto: culparlo
    mandaría a cambiar GROQ_LLM_MODEL sin motivo. Debe salir como un rechazo de
    la petición, que es lo que dispara la degradación a modo JSON.
    """
    with pytest.raises(AIProviderUnavailable) as error:
        raise_for_status(
            _Response(400, "This model does not support response format `json_schema`.")
        )

    assert "no reconoce el modelo" not in str(error.value)
    assert "rechazó la petición" in str(error.value)


def test_un_4xx_cualquiera_no_entra_al_backoff():
    """
    Un formato de salida no admitido es permanente.

    Sale como `AIProviderUnavailable` —que no es un `RequestException`— para que
    tenacity no gaste cuatro intentos con espera en algo que nunca va a mejorar.
    """
    with pytest.raises(AIProviderUnavailable) as error:
        raise_for_status(_Response(400, "response_format json_schema is not supported"))

    assert not isinstance(error.value, requests.RequestException)


def test_un_5xx_si_entra_al_backoff():
    """Un fallo transitorio del servidor sale como RequestException: se reintenta."""
    with pytest.raises(requests.HTTPError):
        raise_for_status(_Response(503, "Service Unavailable"))


def test_una_respuesta_correcta_no_levanta_nada():
    assert raise_for_status(_Response(200)) is None


# ── Cuánto esperar tras un 429 ───────────────────────────────
def test_prefiere_la_cabecera_retry_after():
    assert retry_after(_Response(429, "", {"retry-after": "12"}), "") == 12.0


def test_usa_la_reposicion_de_tokens_si_no_hay_retry_after():
    """El cupo de tokens por minuto es el límite que se toca en el nivel gratuito."""
    delay = retry_after(_Response(429, "", {"x-ratelimit-reset-tokens": "29.055s"}), "")

    assert pytest.approx(delay, abs=0.1) == 30.0


def test_entiende_la_duracion_compuesta():
    delay = retry_after(_Response(429, "", {"x-ratelimit-reset-requests": "4m19.2s"}), "")

    assert pytest.approx(delay, abs=0.1) == 260.2


def test_cae_al_mensaje_cuando_no_hay_cabeceras():
    delay = retry_after(_Response(429), "Rate limit reached. Please try again in 7.5s.")

    assert pytest.approx(delay, abs=0.1) == 8.5


def test_sin_ninguna_pista_espera_un_valor_prudente():
    assert retry_after(_Response(429), "Rate limit reached") == 20.0


def test_la_espera_de_un_429_nunca_supera_el_techo():
    """Un `4m19.2s` no debe dejar la tarea colgada cuatro minutos."""
    state = SimpleNamespace(outcome=SimpleNamespace(exception=lambda: RateLimited("", 260.0)))

    assert retry_wait(state) == MAX_RATE_LIMIT_WAIT
