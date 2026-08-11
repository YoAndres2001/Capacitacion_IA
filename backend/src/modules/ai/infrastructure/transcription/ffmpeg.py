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
    Extrae el audio a FLAC 16 kHz mono: el formato que recomienda Groq Whisper.

    16 kHz mono es la frecuencia a la que Whisper trabaja internamente, así que
    no se pierde información. FLAC es sin pérdida y pesa alrededor de la mitad
    que el WAV equivalente, lo que importa porque el archivo viaja por red hasta
    Groq y hay un tope de tamaño por petición.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(source),
                "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "flac", str(target),
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


@dataclass(frozen=True)
class AudioSlice:
    """Un trozo de audio y el segundo del original en el que empieza."""

    path: Path
    offset_seconds: float


def split_audio(source: Path, out_dir: Path, *, chunk_seconds: int) -> list[AudioSlice]:
    """
    Parte el audio en trozos de duración fija para poder subirlos de uno en uno.

    Cada trozo se **recodifica** en vez de copiarse (`-c copy`): el copiado
    directo corta en el límite de paquete y puede dejar partes con la cabecera
    FLAC incompleta, que Groq rechaza. El audio ya es 16 kHz mono, así que
    recodificar cuesta segundos y garantiza archivos válidos.

    `-reset_timestamps 1` hace que cada parte empiece en 0:00; el
    desplazamiento real respecto del original lo declara ffmpeg en la lista de
    segmentos (`-segment_list`), y es lo que se suma a los timestamps de Groq
    para reconstruir la línea de tiempo global. Sin él, todas las partes
    parecerían empezar al principio del video y las citas del chat apuntarían al
    minuto equivocado.

    El desplazamiento se lee de esa lista y no de `ffprobe`: los FLAC que
    produce el segmentador llevan `total_samples = 0` en su STREAMINFO —el
    muxer no conoce la duración mientras escribe— y `ffprobe` devuelve 0 o la
    duración del archivo completo. Medido en este proyecto sobre 25 s partidos
    en tres: `0.00`, `0.00` y `25.00`. La lista de segmentos, en cambio, la
    escribe el propio ffmpeg con los cortes exactos que aplicó.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "part_%04d.flac")
    listing = out_dir / "segments.csv"

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(source),
                "-f", "segment",
                "-segment_time", str(chunk_seconds),
                "-segment_format", "flac",
                "-segment_list", str(listing),
                "-segment_list_type", "csv",
                "-reset_timestamps", "1",
                "-ac", "1", "-ar", "16000", "-c:a", "flac",
                pattern,
            ],
            capture_output=True,
            text=True,
            timeout=60 * 60,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise AudioExtractionFailed(
            f"No se pudo dividir el audio: {exc.stderr[-500:] if exc.stderr else exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioExtractionFailed("La división del audio superó el tiempo límite.") from exc

    parts = sorted(out_dir.glob("part_*.flac"))
    if not parts:
        raise AudioExtractionFailed("La división del audio no produjo ningún trozo.")

    starts = _segment_starts(listing)
    return [
        AudioSlice(
            path=part,
            # Reserva por si la lista no se pudo leer: el segmentador corta
            # contra la línea de tiempo ABSOLUTA (el corte n se busca a partir
            # del segundo n por chunk_seconds), así que el error se limita a la
            # duración de un frame y no se acumula entre partes.
            offset_seconds=starts.get(part.name, float(index * chunk_seconds)),
        )
        for index, part in enumerate(parts)
    ]


def _segment_starts(listing: Path) -> dict[str, float]:
    """
    Lee `nombre,inicio,fin` de la lista de segmentos de ffmpeg.

    Devuelve `{}` ante cualquier problema: el llamador tiene una reserva
    razonable y quedarse sin trocear el audio sería mucho peor que un
    desplazamiento con precisión de frame.
    """
    if not listing.exists():
        return {}
    try:
        rows = listing.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    starts: dict[str, float] = {}
    for row in rows:
        fields = row.split(",")
        if len(fields) < 2:
            continue
        try:
            starts[Path(fields[0]).name] = float(fields[1])
        except ValueError:
            continue
    return starts


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
