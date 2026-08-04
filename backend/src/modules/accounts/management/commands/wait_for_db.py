"""Espera a que PostgreSQL esté disponible antes de migrar (arranque en Docker)."""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, connection


class Command(BaseCommand):
    help = "Bloquea hasta que la base de datos acepte conexiones."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--timeout", type=int, default=90)
        parser.add_argument("--interval", type=float, default=2.0)

    def handle(self, *args, **options) -> None:
        timeout = options["timeout"]
        interval = options["interval"]
        deadline = time.monotonic() + timeout

        self.stdout.write("Esperando a PostgreSQL...")
        while time.monotonic() < deadline:
            try:
                connection.ensure_connection()
                self.stdout.write(self.style.SUCCESS("Base de datos disponible."))
                return
            except OperationalError:
                time.sleep(interval)

        self.stderr.write(self.style.ERROR(f"La base de datos no respondió en {timeout}s."))
        raise SystemExit(1)
