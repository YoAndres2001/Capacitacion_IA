"""Extracción de audio y metadatos de video con ffmpeg (etapa 1 del pipeline)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.shared.domain.exceptions import DomainError
from src.shared.infrastructure.logging import get_logger

logger = get_logger("ai.ffmpeg")


class AudioExtractionFailed(DomainError):
    code = "AUDIO_EXTRACTION_FAILED"
    default_message = "No se pudo extraer el audio del video."


@dataclass
class MediaInfo:
    duration_seconds: int = 0
    width: int = 0
    height: int = 0
    has_audio: bool = False
    video_codec: str = ""
    audio_codec: str = ""


def probe(path: Path) -> MediaInfo:
    """Metadatos del archivo mediante ffprobe."""
    try:
        output = subprocess.run(
            [
                "ffprobe", "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise AudioExtractionFailed(f"ffprobe falló: {exc}") from exc

    data = json.loads(output or "{}")
    info = MediaInfo()

    duration = data.get("format", {}).get("duration")
    if duration:
        info.duration_seconds = int(float(duration))

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and not info.video_codec:
            info.video_codec = stream.get("codec_name", "")
            info.width = int(stream.get("width") or 0)
            info.height = int(stream.get("height") or 0)
        elif stream.get("codec_type") == "audio":
            info.has_audio = True
            info.audio_codec = stream.get("codec_name", "")

    return info


def extract_audio(source: Path, target: Path) -> Path:
    """
    Extrae el audio a WAV 16 kHz mono PCM: el formato que espera Whisper.

    Convertir aquí evita que el modelo haga la conversión en memoria y reduce
    notablemente el uso de RAM del worker.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(source),
                "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", "-f", "wav", str(target),
            ],
            capture_output=True,
            text=True,
            timeout=60 * 60 * 2,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise AudioExtractionFailed(f"ffmpeg falló: {exc.stderr[-500:] if exc.stderr else exc}") from exc
    except FileNotFoundError as exc:
        raise AudioExtractionFailed("ffmpeg no está instalado en este contenedor.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioExtractionFailed("La extracción de audio superó el tiempo límite.") from exc

    if not target.exists() or target.stat().st_size == 0:
        raise AudioExtractionFailed("El audio extraído está vacío.")
    return target


def extract_thumbnail(source: Path, target: Path, *, at_second: int = 3) -> Path | None:
    """Miniatura para la tarjeta del curso. Su fallo nunca interrumpe la ingesta."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(at_second), "-i", str(source),
                "-vframes", "1", "-vf", "scale=640:-1", str(target),
            ],
            capture_output=True,
            timeout=120,
            check=True,
        )
        return target if target.exists() else None
    except Exception:
        logger.warning("No se pudo generar la miniatura", extra={"source": str(source)})
        return None
