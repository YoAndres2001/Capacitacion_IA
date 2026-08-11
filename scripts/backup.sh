#!/usr/bin/env bash
# Respaldo de PostgreSQL, media e índices FAISS (RNF-33).
# Uso:  ./scripts/backup.sh [directorio-destino]
set -euo pipefail

DEST="${1:-./backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$DEST"

echo "==> Respaldando base de datos"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-nexora}" \
  -d "${POSTGRES_DB:-nexora}" --clean --if-exists \
  | gzip > "$DEST/db_$STAMP.sql.gz"

echo "==> Respaldando media (videos y documentos)"
docker run --rm \
  -v projectcapacitacionia_media_data:/data:ro \
  -v "$(pwd)/$DEST":/backup \
  alpine tar czf "/backup/media_$STAMP.tar.gz" -C /data .

echo "==> Respaldando índices FAISS"
# Reconstruibles desde PostgreSQL, pero respaldarlos acelera la recuperación.
docker run --rm \
  -v projectcapacitacionia_faiss_indices:/data:ro \
  -v "$(pwd)/$DEST":/backup \
  alpine tar czf "/backup/indices_$STAMP.tar.gz" -C /data .

echo "==> Listo. Archivos en $DEST:"
ls -lh "$DEST" | grep "$STAMP"
