#!/usr/bin/env bash
# Restauración desde un respaldo.
# Uso:  ./scripts/restore.sh backups/db_20260803_120000.sql.gz
set -euo pipefail

DUMP="${1:?Indique el archivo .sql.gz a restaurar}"

echo "ATENCIÓN: se reemplazará el contenido de la base de datos actual."
read -r -p "Escriba 'CONFIRMAR' para continuar: " answer
[ "$answer" = "CONFIRMAR" ] || { echo "Cancelado."; exit 1; }

echo "==> Restaurando $DUMP"
gunzip -c "$DUMP" | docker compose exec -T postgres psql \
  -U "${POSTGRES_USER:-capacita}" -d "${POSTGRES_DB:-capacita}"

echo "==> Aplicando migraciones pendientes"
docker compose exec -T backend python manage.py migrate --noinput

echo "==> Reconstruya los índices vectoriales de cada proyecto desde la UI"
echo "    (Proyectos → Reconstruir índice) o con la tarea rebuild_project_index."
echo "Listo."
