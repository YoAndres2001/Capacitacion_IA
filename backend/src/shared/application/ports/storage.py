"""Puerto de almacenamiento de archivos."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO


class StoragePort(ABC):
    """Abstracción del almacenamiento (disco local hoy, S3 mañana)."""

    @abstractmethod
    def save(self, relative_path: str, content: BinaryIO) -> str:
        """Guarda el contenido y devuelve la ruta relativa definitiva."""

    @abstractmethod
    def open(self, relative_path: str) -> BinaryIO: ...

    @abstractmethod
    def delete(self, relative_path: str) -> None: ...

    @abstractmethod
    def exists(self, relative_path: str) -> bool: ...

    @abstractmethod
    def absolute_path(self, relative_path: str) -> Path:
        """Ruta física; necesaria para ffmpeg/Whisper, que trabajan con archivos."""

    @abstractmethod
    def url(self, relative_path: str, *, expires_in: int = 14_400) -> str:
        """URL de acceso (firmada y con expiración cuando el backend lo soporta)."""

    @abstractmethod
    def size(self, relative_path: str) -> int: ...
