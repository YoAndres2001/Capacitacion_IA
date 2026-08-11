"""
Mide la latencia real de Groq y de los embeddings locales.

Sirve para elegir el modelo correcto (GROQ_LLM_MODEL, EMBEDDING_MODEL) antes de
procesar material de verdad.

Uso:  python manage.py ai_bench
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from src.modules.ai.application.ports.llm import ChatMessage
from src.shared.container import get_embeddings, get_llm


class Command(BaseCommand):
    help = "Diagnóstico de rendimiento de Groq (LLM) y de los embeddings locales."

    def handle(self, *args, **options) -> None:
        llm = get_llm()
        embeddings = get_embeddings()

        self.stdout.write("")
        self.stdout.write(f"Proveedor .............. {llm.provider_name}")
        self.stdout.write(f"Modelo LLM ............. {llm.model_name}")
        self.stdout.write(
            f"Modelo de embeddings ... {embeddings.model_name} ({embeddings.provider_name})"
        )

        available = llm.is_available()
        self.stdout.write(
            f"Disponible ............. "
            + (self.style.SUCCESS("sí") if available else self.style.ERROR("no"))
        )
        if not available:
            self.stdout.write(self.style.ERROR("\nEl proveedor no responde. Revise el servicio."))
            return

        self.stdout.write("\n" + "-" * 62)

        # Los embeddings son locales y el LLM remoto: un fallo al cargar el
        # modelo local no debe ocultar el resto del diagnóstico.
        started = time.monotonic()
        try:
            vector = embeddings.embed_query("inventario cíclico")
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Embedding de consulta ... falló: {exc}"))
        else:
            elapsed = time.monotonic() - started
            self.stdout.write(f"Embedding de consulta ... {len(vector)} dims · {elapsed:.1f} s")

        started = time.monotonic()
        response = llm.generate(
            [ChatMessage(role="user", content="En una sola frase: ¿qué es un inventario?")],
            max_tokens=80,
        )
        short_elapsed = time.monotonic() - started
        self.stdout.write(f"Generación corta ........ {short_elapsed:.1f} s")
        self.stdout.write(f"   → {response.content.strip()[:150]}")

        started = time.monotonic()
        payload, usage = llm.generate_json(
            [
                ChatMessage(
                    role="system", content="Devuelves SIEMPRE JSON válido, sin texto adicional."
                ),
                ChatMessage(
                    role="user",
                    content=(
                        'Devuelve {"chapters": [{"title": "...", "summary": "..."}]} con dos '
                        "capítulos sobre control de inventario."
                    ),
                ),
            ]
        )
        json_elapsed = time.monotonic() - started
        self.stdout.write(f"Salida JSON estructurada  {json_elapsed:.1f} s")
        self.stdout.write(f"   → {str(payload)[:180]}")
        self.stdout.write(f"   → tokens: {usage.prompt_tokens} in / {usage.completion_tokens} out")

        self.stdout.write("-" * 62)
        self._verdict(json_elapsed)

    def _verdict(self, json_elapsed: float) -> None:
        """
        La ingesta ejecuta 4 cadenas JSON con prompts bastante mayores que este.
        Una regla práctica: si esta prueba tarda más de ~30 s, el análisis
        completo no terminará dentro del timeout.
        """
        estimate = json_elapsed * 4 * 6  # 4 cadenas, prompts ~6× más largos
        self.stdout.write(f"\nAnálisis completo estimado: ~{estimate / 60:.0f} min por material.")

        if json_elapsed < 10:
            self.stdout.write(self.style.SUCCESS("Configuración adecuada para este hardware."))
        elif json_elapsed < 30:
            self.stdout.write(
                self.style.WARNING(
                    "Funcional pero lento. Considere bajar AI_ANALYSIS_MAX_CHARS."
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "Demasiado lento para ser Groq: casi siempre significa límite de uso "
                    "(429) con reintentos de por medio.\n"
                    "Revise la cuota en https://console.groq.com o pruebe "
                    "GROQ_LLM_MODEL=llama-3.1-8b-instant."
                )
            )
