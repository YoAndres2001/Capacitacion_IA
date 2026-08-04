"""
Diagnóstico fino del proveedor local: mide tokens/s bajo distintas condiciones.

Sirve para separar "el modelo es lento" de "algo en la configuración lo está
frenando". Uso:

    python manage.py ai_probe
"""

from __future__ import annotations

import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

PROMPT = "Responde en tres frases: ¿qué es el inventario cíclico y cómo se clasifica ABC?"


class Command(BaseCommand):
    help = "Mide tokens/s del LLM local con y sin modo JSON, y con distintos contextos."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--model", default=None)
        parser.add_argument("--predict", type=int, default=120)

    def handle(self, *args, **options) -> None:
        config = settings.AI_SETTINGS["OLLAMA"]
        model = options["model"] or config["LLM_MODEL"]
        url = f"{config['BASE_URL'].rstrip('/')}/api/chat"
        predict = options["predict"]

        self.stdout.write(f"\nModelo: {model}   (num_predict={predict})")
        self.stdout.write("-" * 68)
        self.stdout.write(f"{'escenario':<28}{'tiempo':>9}{'salida':>8}{'tok/s':>9}")
        self.stdout.write("-" * 68)

        escenarios = [
            ("texto libre · ctx 8192", None, 8192),
            ("JSON forzado · ctx 8192", "json", 8192),
            ("texto libre · ctx 2048", None, 2048),
            ("JSON forzado · ctx 2048", "json", 2048),
        ]

        resultados: dict[str, float] = {}
        for nombre, formato, ctx in escenarios:
            rate = self._medir(url, model, formato, ctx, predict, nombre)
            if rate:
                resultados[nombre] = rate

        self.stdout.write("-" * 68)
        self._conclusion(resultados)

    def _medir(self, url, model, formato, ctx, predict, nombre) -> float | None:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            "stream": False,
            "options": {"temperature": 0, "num_predict": predict, "num_ctx": ctx},
        }
        if formato:
            body["format"] = formato

        started = time.monotonic()
        try:
            data = requests.post(url, json=body, timeout=900).json()
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"{nombre:<28} error: {exc}"))
            return None

        elapsed = time.monotonic() - started
        produced = int(data.get("eval_count") or 0)
        rate = produced / elapsed if elapsed else 0.0

        self.stdout.write(f"{nombre:<28}{elapsed:8.1f}s{produced:8d}{rate:9.1f}")
        return rate

    def _conclusion(self, resultados: dict[str, float]) -> None:
        libre = resultados.get("texto libre · ctx 8192")
        json_forzado = resultados.get("JSON forzado · ctx 8192")
        ctx_chico = resultados.get("texto libre · ctx 2048")

        if not libre:
            return

        if json_forzado and libre / json_forzado >= 1.6:
            self.stdout.write(
                self.style.WARNING(
                    f"\nEl modo JSON forzado cuesta {libre / json_forzado:.1f}× más tiempo.\n"
                    "Conviene pedir el JSON por prompt y parsear con tolerancia."
                )
            )
        if ctx_chico and ctx_chico / libre >= 1.3:
            self.stdout.write(
                self.style.WARNING(
                    f"\nReducir num_ctx a 2048 acelera {ctx_chico / libre:.1f}×."
                )
            )

        if libre < 5:
            self.stdout.write(
                self.style.ERROR(
                    f"\n{libre:.1f} tok/s es muy bajo para un modelo pequeño. "
                    "Revise cuántos núcleos y cuánta memoria tiene asignada la VM de "
                    "Docker: es el factor que más pesa en Windows/WSL2."
                )
            )
        elif libre < 15:
            self.stdout.write(f"\n{libre:.1f} tok/s: aceptable en CPU.")
        else:
            self.stdout.write(self.style.SUCCESS(f"\n{libre:.1f} tok/s: buen rendimiento."))
