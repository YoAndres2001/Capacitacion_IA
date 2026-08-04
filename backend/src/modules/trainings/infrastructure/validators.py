"""
Validación de archivos subidos (RNF-23).

Se valida la extensión, el tamaño y — lo importante — el **MIME real** leído de
los primeros bytes del archivo, no el que declara el cliente.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from django.conf import settings

from src.shared.domain.exceptions import FileTooLarge, InvalidFileType

#: extensión → tipo de material
EXTENSION_TO_TYPE = {
    ".mp4": "VIDEO", ".mov": "VIDEO", ".mkv": "VIDEO", ".webm": "VIDEO", ".avi": "VIDEO",
    ".mp3": "AUDIO", ".wav": "AUDIO", ".m4a": "AUDIO", ".ogg": "AUDIO",
    ".pdf": "PDF",
    ".docx": "DOCX",
    ".pptx": "PPTX",
    ".txt": "TXT",
    ".md": "MD",
}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str) -> str:
    """Nombre seguro: sin rutas, sin acentos, sin caracteres especiales."""
    base = Path(name).name
    normalized = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    cleaned = _SAFE_NAME.sub("_", normalized).strip("._") or "archivo"
    return cleaned[:200]


def material_type_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    material_type = EXTENSION_TO_TYPE.get(suffix)
    if material_type is None:
        allowed = ", ".join(sorted(EXTENSION_TO_TYPE))
        raise InvalidFileType(f"Extensión '{suffix}' no permitida. Permitidas: {allowed}.")
    return material_type


def max_size_bytes(material_type: str) -> int:
    limits = settings.STORAGE_SETTINGS
    mb = limits["MAX_VIDEO_SIZE_MB"] if material_type in {"VIDEO", "AUDIO"} else limits["MAX_DOCUMENT_SIZE_MB"]
    return mb * 1024 * 1024


def validate_declared(filename: str, size_bytes: int) -> str:
    """Validación previa a la carga (upload-session): extensión y tamaño."""
    material_type = material_type_for(filename)
    limit = max_size_bytes(material_type)
    if size_bytes > limit:
        raise FileTooLarge(
            f"El archivo pesa {size_bytes / 1_048_576:.1f} MB y el máximo es "
            f"{limit / 1_048_576:.0f} MB."
        )
    if size_bytes <= 0:
        raise InvalidFileType("El archivo está vacío.")
    return material_type


def detect_mime(path: Path) -> str:
    """MIME real a partir del contenido; si `python-magic` no está, cae al mimetype por extensión."""
    try:
        import magic  # type: ignore

        return magic.from_file(str(path), mime=True)
    except Exception:  # pragma: no cover - libmagic ausente en algunos entornos
        import mimetypes

        return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def validate_real_content(path: Path, material_type: str) -> str:
    """
    Confirma que el contenido corresponde al tipo declarado.

    Un `.pdf` renombrado a `.mp4` se detecta aquí y se rechaza.
    """
    detected = detect_mime(path)
    allowed = settings.ALLOWED_UPLOAD_TYPES.get(material_type, {}).get("mimes", set())

    # text/plain cubre TXT y MD; algunos sistemas reportan variantes.
    if material_type in {"TXT", "MD"} and detected.startswith("text/"):
        return detected

    if allowed and detected not in allowed:
        raise InvalidFileType(
            f"El contenido del archivo es '{detected}', que no corresponde a un {material_type}."
        )
    return detected


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
