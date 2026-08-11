"""
Comprobaciones de configuración de IA que se ejecutan al arrancar.

Groq es el único proveedor externo: sin `GROQ_API_KEY` no hay chat, análisis,
exámenes ni transcripción. Detectarlo al inicio —y no en mitad de una ingesta de
20 minutos— ahorra un diagnóstico incómodo.

Se emite como *warning* y no como *error* para que `migrate`, `collectstatic` y
las pruebas sigan funcionando sin credencial; el fallo duro y con mensaje claro
lo da `groq_http.require_api_key()` en la primera llamada real.
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Warning, register


@register()
def check_groq_api_key(app_configs, **kwargs):
    """`GROQ_API_KEY` debe llegar por variable de entorno."""
    if settings.AI_SETTINGS["GROQ"]["API_KEY"]:
        return []

    return [
        Warning(
            "Falta GROQ_API_KEY: las funciones de IA no estarán disponibles.",
            hint=(
                "Groq es el único proveedor externo de IA de la plataforma. "
                "Obtenga una clave en https://console.groq.com/keys y defínala "
                "como variable de entorno GROQ_API_KEY (por ejemplo, en el .env "
                "que consume docker compose). Nunca la escriba en el código."
            ),
            id="ai.W001",
        )
    ]
