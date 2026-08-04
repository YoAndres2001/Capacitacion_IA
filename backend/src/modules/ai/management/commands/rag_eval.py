"""
Evaluación de calidad del RAG (docs/11-diseno-rag.md §10).

Ejecuta un *golden set* de preguntas contra una capacitación y reporta
groundedness, tasa de respuesta y latencia. Sirve como test de regresión al
cambiar de modelo o ajustar los umbrales del recuperador.

Uso:
    python manage.py rag_eval --training <uuid> [--file golden.json]

Formato del archivo (opcional):
    [{"question": "¿Qué es el inventario cíclico?", "expect_grounded": true}]
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

DEFAULT_QUESTIONS = [
    {"question": "¿De qué trata esta capacitación?", "expect_grounded": True},
    {"question": "Resume los puntos principales del contenido.", "expect_grounded": True},
    {"question": "¿Cuáles son los conceptos clave?", "expect_grounded": True},
    # Control negativo: no está en el material, la IA DEBE decir que no sabe.
    {"question": "¿Cuál es la capital de Mongolia?", "expect_grounded": False},
]


class Command(BaseCommand):
    help = "Evalúa la calidad del RAG de una capacitación con un golden set."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--training", required=True, help="UUID de la capacitación")
        parser.add_argument("--file", help="Archivo JSON con el golden set")
        parser.add_argument("--top-k", type=int, default=None)

    def handle(self, *args, **options) -> None:
        from src.modules.ai.domain.rag_policies import GroundingPolicy
        from src.modules.ai.presentation.views import build_retriever
        from src.modules.trainings.infrastructure.models import Training

        training = (
            Training.objects.select_related("project")
            .filter(id=options["training"])
            .first()
        )
        if training is None:
            raise CommandError("La capacitación indicada no existe.")

        questions = DEFAULT_QUESTIONS
        if options["file"]:
            path = Path(options["file"])
            if not path.exists():
                raise CommandError(f"No se encontró el archivo {path}.")
            questions = json.loads(path.read_text(encoding="utf-8"))

        retriever = build_retriever(training.project_id)
        policy = GroundingPolicy()

        self.stdout.write(f"\nEvaluando RAG · {training.title}\n" + "=" * 70)

        grounded_hits = 0
        expected_grounded = 0
        correct = 0
        latencies: list[float] = []

        for item in questions:
            question = item["question"]
            expected = bool(item.get("expect_grounded", True))
            expected_grounded += int(expected)

            started = time.monotonic()
            chunks = retriever.retrieve(
                question,
                training_id=training.id,
                project_id=training.project_id,
                top_k=options["top_k"],
            )
            decision = policy.evaluate(chunks)
            elapsed = (time.monotonic() - started) * 1000
            latencies.append(elapsed)

            ok = decision.is_grounded == expected
            correct += int(ok)
            grounded_hits += int(decision.is_grounded)

            mark = self.style.SUCCESS("OK  ") if ok else self.style.ERROR("FALLA")
            best = max((chunk.score for chunk in chunks), default=0.0)
            self.stdout.write(
                f"{mark} {question[:58]:<58} "
                f"grounded={str(decision.is_grounded):<5} "
                f"top={best:.2f} {elapsed:.0f} ms"
            )
            if not decision.is_grounded and decision.reason:
                self.stdout.write(f"       motivo: {decision.reason}")

        total = len(questions)
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(f"Preguntas evaluadas ....... {total}")
        self.stdout.write(f"Comportamiento esperado ... {correct}/{total} ({correct / total:.0%})")
        self.stdout.write(
            f"Respondidas con contexto .. {grounded_hits}/{total} "
            f"(esperadas: {expected_grounded})"
        )
        self.stdout.write(
            f"Latencia recuperación ..... media {sum(latencies) / len(latencies):.0f} ms · "
            f"máx {max(latencies):.0f} ms"
        )

        if correct < total:
            self.stdout.write(
                self.style.WARNING(
                    "\nHay desviaciones: revise los umbrales RETRIEVER_MIN_SCORE / "
                    "RETRIEVER_MIN_TOP_SCORE o la cobertura del material."
                )
            )
