"""
Reconstruye los índices FAISS con el modelo de embeddings actual.

Necesario cuando cambia `EMBEDDING_MODEL`: un índice de 768 dimensiones y un
modelo que genera 384 no se pueden mezclar, y buscar contra el índice antiguo
aborta dentro de FAISS. Los `chunks` de PostgreSQL son la fuente de verdad
(RN-10), así que el índice siempre se puede regenerar.

Uso:
    python manage.py rebuild_indices                 # solo los incompatibles
    python manage.py rebuild_indices --all           # todos los proyectos
    python manage.py rebuild_indices --project <id>  # uno concreto
    python manage.py rebuild_indices --async         # delega en Celery
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from src.shared.container import get_embeddings


class Command(BaseCommand):
    help = "Reconstruye los índices FAISS cuyo modelo de embeddings ya no coincide."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--project", default=None, help="UUID de un proyecto concreto.")
        parser.add_argument(
            "--all",
            action="store_true",
            help="Reconstruye todos los proyectos, coincida o no la dimensión.",
        )
        parser.add_argument(
            "--async",
            dest="run_async",
            action="store_true",
            help="Encola la reconstrucción en Celery en vez de ejecutarla aquí.",
        )

    def handle(self, *args, **options) -> None:
        from src.modules.ai.infrastructure.tasks import rebuild_project_index
        from src.modules.projects.infrastructure.models import VectorCollection

        embeddings = get_embeddings()
        dimension = embeddings.dimension
        self.stdout.write(
            f"Modelo de embeddings actual: {embeddings.model_name} ({dimension} dimensiones)\n"
        )

        if options["project"]:
            try:
                targets = [str(UUID(options["project"]))]
            except ValueError as exc:
                raise CommandError(f"'{options['project']}' no es un UUID válido.") from exc
        else:
            targets = [
                str(project_id)
                for project_id in VectorCollection.objects.values_list("project_id", flat=True)
            ]

        if not targets:
            self.stdout.write("No hay índices registrados. Nada que reconstruir.")
            return

        pending = [
            project_id
            for project_id in targets
            if options["all"] or self._is_incompatible(project_id, dimension)
        ]

        if not pending:
            self.stdout.write(
                self.style.SUCCESS("Todos los índices coinciden con el modelo actual.")
            )
            return

        self.stdout.write(f"Índices a reconstruir: {len(pending)}\n")
        for project_id in pending:
            if options["run_async"]:
                rebuild_project_index.delay(project_id)
                self.stdout.write(f"  {project_id} · encolado")
                continue
            try:
                result = rebuild_project_index(project_id)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  {project_id} · falló: {exc}"))
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"  {project_id} · {result['vectors']} vectores")
                )

        self.stdout.write("")

    @staticmethod
    def _is_incompatible(project_id: str, dimension: int) -> bool:
        """
        Un índice sin `meta.json` legible se considera incompatible.

        Reconstruirlo de más cuesta unos minutos de CPU; dejarlo cuando de verdad
        no coincide deja el chat sin contexto de forma silenciosa.
        """
        meta_path = Path(settings.RAG_SETTINGS["INDEX_ROOT"]) / project_id / "meta.json"
        if not meta_path.exists():
            return True
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True
        return int(meta.get("dimension") or 0) != dimension
