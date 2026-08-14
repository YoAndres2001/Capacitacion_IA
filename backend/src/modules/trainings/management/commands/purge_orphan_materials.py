"""
Retira el material que quedó vivo bajo una capacitación borrada.

El borrado lógico de Django no cascadea. Antes de que `TrainingViewSet`
retirara el material al borrar la capacitación, esos archivos quedaban activos:
su `sha256` seguía ocupando el hueco del proyecto —impidiendo volver a subir el
mismo archivo— y sus fragmentos seguían respondiendo en el chat.

Este comando limpia esa deuda. Es idempotente.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from src.modules.trainings.application.use_cases.discard_material import discard_materials
from src.modules.trainings.infrastructure.models import Material, Training


class Command(BaseCommand):
    help = "Retira el material que sigue activo bajo capacitaciones ya borradas."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que se retiraría, sin tocar la base de datos.",
        )

    def handle(self, *args, **options) -> None:
        deleted_trainings = Training.all_objects.filter(deleted_at__isnull=False)
        orphans = Material.objects.filter(
            lesson__module__training__in=deleted_trainings
        ).select_related("lesson__module__training", "project")

        if not orphans.exists():
            self.stdout.write(self.style.SUCCESS("No hay material huérfano."))
            return

        for material in orphans:
            self.stdout.write(
                f"  · {material.original_filename} "
                f"(proyecto «{material.project.name}», "
                f"capacitación «{material.lesson.module.training.title}»)"
            )

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(f"[dry-run] Se retirarían {orphans.count()} material(es).")
            )
            return

        with transaction.atomic():
            count = discard_materials(orphans)

        self.stdout.write(
            self.style.SUCCESS(
                f"{count} material(es) retirado(s). "
                "Las colecciones vectoriales afectadas quedaron marcadas para reconstruirse."
            )
        )
