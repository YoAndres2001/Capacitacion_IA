"""Implementación de `StoragePort` sobre el sistema de archivos local."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import BinaryIO

from django.conf import settings
from django.core.signing import TimestampSigner

from src.shared.application.ports.storage import StoragePort


class LocalStorage(StoragePort):
    """
    Guarda los archivos bajo MEDIA_ROOT.

    Los videos NO se sirven públicamente: `url()` devuelve una ruta firmada que
    el backend valida antes de delegar la entrega a nginx (X-Accel-Redirect).
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.MEDIA_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        self._signer = TimestampSigner(salt="nexora.media")

    # ── Escritura/lectura ────────────────────────────────────
    def save(self, relative_path: str, content: BinaryIO) -> str:
        target = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        with tmp.open("wb") as fh:
            shutil.copyfileobj(content, fh, length=1024 * 1024)
        tmp.replace(target)  # escritura atómica
        return relative_path

    def open(self, relative_path: str) -> BinaryIO:
        return self._resolve(relative_path).open("rb")

    def delete(self, relative_path: str) -> None:
        target = self._resolve(relative_path)
        if target.exists():
            target.unlink()
            # Limpia directorios vacíos del material
            parent = target.parent
            try:
                if parent != self.root and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass

    def exists(self, relative_path: str) -> bool:
        return self._resolve(relative_path).exists()

    def absolute_path(self, relative_path: str) -> Path:
        return self._resolve(relative_path)

    def size(self, relative_path: str) -> int:
        return self._resolve(relative_path).stat().st_size

    def url(self, relative_path: str, *, expires_in: int = 14_400) -> str:
        token = self._signer.sign(relative_path)
        return f"/api/v1/media/{token}"

    def verify_signed(self, token: str, *, max_age: int = 14_400) -> str:
        """Valida una URL firmada y devuelve la ruta relativa."""
        return self._signer.unsign(token, max_age=max_age)

    # ── Utilidades ───────────────────────────────────────────
    @staticmethod
    def sha256_of(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _resolve(self, relative_path: str) -> Path:
        # Evita traversal: la ruta resultante debe quedar dentro de root.
        candidate = (self.root / relative_path.lstrip("/")).resolve()
        root = self.root.resolve()
        if not str(candidate).startswith(str(root)):
            raise ValueError(f"Ruta fuera del almacenamiento: {relative_path}")
        return candidate
