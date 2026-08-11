"""
Transcripción con la API Speech-to-Text de Groq (Whisper).

Sustituye a `faster-whisper`: ya no se carga ningún modelo local ni se descargan
pesos en el worker. Groq es el único servicio externo que interviene.

**Los timestamps son la razón de ser de este adaptador.** El chat debe poder
responder "esto aparece en el minuto 12:43 del video", y para eso cada segmento
conserva su `start`/`end` en la línea de tiempo del video ORIGINAL. Cuando el
audio no cabe en una sola petición se parte en trozos, y a cada trozo se le suma
su desplazamiento antes de unir el resultado (ver `_transcribe_in_slices`).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

import requests
from tenacity import retry

from src.shared.domain.exceptions import DomainError
from src.shared.infrastructure.logging import get_logger

from ...application.ports.transcriber import (
    TranscriberPort,
    TranscriptionResult,
    TranscriptSegment,
)
from ..providers.groq_http import auth_headers, config, raise_for_status, retry_policy
from . import ffmpeg

logger = get_logger("ai.transcription")

#: Tope de subida por petición. Groq admite 25 MB en el nivel gratuito y 100 MB
#: en el de desarrollo; se usa el menor con margen para las cabeceras multipart.
MAX_UPLOAD_BYTES = 24 * 1024 * 1024

#: Duración de cada trozo cuando hay que dividir. A 16 kHz mono FLAC son unos
#: 5-6 MB por trozo: entra de sobra y mantiene bajo el número de peticiones.
CHUNK_SECONDS = 600

_RETRY = retry_policy()


class TranscriptionFailed(DomainError):
    code = "TRANSCRIPTION_FAILED"
    default_message = "No se pudo transcribir el audio."


class NoSpeechDetected(DomainError):
    code = "NO_SPEECH_DETECTED"
    default_message = "No se detectó voz en el audio."


class GroqTranscriber(TranscriberPort):
    def __init__(self, model: str | None = None) -> None:
        settings_groq = config()
        self._model = model or settings_groq["WHISPER_MODEL"]
        self._base_url = settings_groq["BASE_URL"].rstrip("/")
        self._timeout = settings_groq.get("TRANSCRIBE_TIMEOUT", 600)

    @property
    def model_name(self) -> str:
        return f"groq-{self._model}"

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> TranscriptionResult:
        size = audio_path.stat().st_size if audio_path.exists() else 0
        if not size:
            raise TranscriptionFailed("El archivo de audio está vacío.")

        if size <= MAX_UPLOAD_BYTES:
            payload = self._send(audio_path, _normalize_language(language or "") or None)
            segments = _segments_from(payload, offset=0.0)
            detected = payload.get("language") or language or ""
            duration = float(payload.get("duration") or 0.0)
            if on_progress:
                on_progress(99)
        else:
            segments, detected, duration = self._transcribe_in_slices(
                audio_path, language, on_progress
            )

        if not segments:
            raise NoSpeechDetected

        # Se reindexa al final: con varios trozos los índices locales de cada uno
        # empiezan otra vez en 0 y el orden global se perdería.
        segments = [
            TranscriptSegment(index=position, start=s.start, end=s.end, text=s.text)
            for position, s in enumerate(segments)
        ]

        return TranscriptionResult(
            # "es" como último recurso: el campo alimenta `Material.language`,
            # que la interfaz muestra y la búsqueda full-text usa como
            # configuración del diccionario.
            language=_normalize_language(detected) or "es",
            segments=segments,
            duration=duration or segments[-1].end,
            model=self.model_name,
            # La API no devuelve probabilidad de idioma. Se informa 0.0 en vez de
            # inventar una cifra: el campo es orientativo en la interfaz.
            confidence=0.0,
        )

    # ── Audio largo: dividir, transcribir y recomponer ────────
    def _transcribe_in_slices(
        self,
        audio_path: Path,
        language: str | None,
        on_progress: Callable[[int], None] | None,
    ) -> tuple[list[TranscriptSegment], str, float]:
        work_dir = audio_path.parent / f"{audio_path.stem}_parts"
        shutil.rmtree(work_dir, ignore_errors=True)

        try:
            slices = ffmpeg.split_audio(audio_path, work_dir, chunk_seconds=CHUNK_SECONDS)
            logger.info(
                "Audio dividido para transcripción",
                extra={"parts": len(slices), "chunk_seconds": CHUNK_SECONDS},
            )

            segments: list[TranscriptSegment] = []
            detected = _normalize_language(language or "")
            duration = 0.0

            for position, piece in enumerate(slices):
                # El idioma detectado en el primer trozo se reutiliza en los
                # siguientes: fijarlo evita que Whisper cambie de criterio a
                # mitad del video, y ahorra la detección en cada petición.
                #
                # Se envía SIEMPRE normalizado a código ISO. Groq devuelve el
                # nombre ("Spanish") pero su parámetro `language` solo acepta el
                # código ("es"): reenviar lo recibido tal cual hacía fallar con
                # 400 todos los trozos a partir del segundo.
                payload = self._send(piece.path, detected or None)
                # El desplazamiento del trozo se suma a cada timestamp: así el
                # minuto que se cita sigue siendo el del video completo.
                segments.extend(_segments_from(payload, offset=piece.offset_seconds))

                detected = detected or _normalize_language(payload.get("language") or "")
                part_duration = float(payload.get("duration") or 0.0)
                duration = max(duration, piece.offset_seconds + part_duration)

                if on_progress:
                    on_progress(min(99, int((position + 1) / len(slices) * 100)))

            return segments, detected, duration
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    # ── Llamada a la API ─────────────────────────────────────
    @retry(**_RETRY)
    def _send(self, audio_path: Path, language: str | None) -> dict[str, Any]:
        """
        Una petición de transcripción, con reintentos y respeto del 429.

        `verbose_json` + `timestamp_granularities[]=segment` es lo que devuelve
        los segmentos con `start`/`end`; sin eso solo llega el texto plano y se
        perderían las citas por minuto.
        """
        data: list[tuple[str, str]] = [
            ("model", self._model),
            ("response_format", "verbose_json"),
            ("timestamp_granularities[]", "segment"),
        ]
        if language:
            data.append(("language", language))

        try:
            with audio_path.open("rb") as handle:
                response = requests.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers=auth_headers(),
                    files={"file": (audio_path.name, handle, "audio/flac")},
                    data=data,
                    timeout=self._timeout,
                )
            raise_for_status(response)
            return response.json()
        except requests.RequestException as exc:
            # El mensaje nunca incluye la cabecera Authorization.
            logger.warning(f"Fallo al transcribir con Groq: {exc}")
            raise
        except OSError as exc:
            raise TranscriptionFailed(f"No se pudo leer el audio: {exc}") from exc


def _segments_from(payload: dict[str, Any], *, offset: float) -> list[TranscriptSegment]:
    """
    Convierte la respuesta de Groq en segmentos con timestamps ABSOLUTOS.

    Si la respuesta no trajera segmentos (modelo o formato inesperado), se
    devuelve el texto completo como un único segmento en lugar de perderlo: el
    RAG seguirá funcionando aunque la cita temporal sea menos precisa.
    """
    raw_segments = payload.get("segments") or []
    segments = [
        TranscriptSegment(
            index=position,
            start=round(float(item.get("start") or 0.0) + offset, 2),
            end=round(float(item.get("end") or 0.0) + offset, 2),
            text=text,
        )
        for position, item in enumerate(raw_segments)
        if (text := (item.get("text") or "").strip())
    ]
    if segments:
        return segments

    text = (payload.get("text") or "").strip()
    if not text:
        return []
    end = round(offset + float(payload.get("duration") or 0.0), 2)
    return [TranscriptSegment(index=0, start=round(offset, 2), end=end, text=text)]


#: Groq devuelve el idioma por su nombre en inglés; su parámetro `language`, en
#: cambio, solo acepta el código ISO-639-1. Se cubren los idiomas plausibles en
#: la plataforma; el resto se deja sin traducir antes que adivinar mal.
_LANGUAGE_CODES = {
    "spanish": "es",
    "english": "en",
    "portuguese": "pt",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "catalan": "ca",
    "galician": "gl",
    "basque": "eu",
    "dutch": "nl",
    "chinese": "zh",
    "japanese": "ja",
    "korean": "ko",
    "russian": "ru",
    "arabic": "ar",
}


def _normalize_language(value: str) -> str:
    """
    Traduce el idioma a un código ISO de dos letras, o devuelve "" si no puede.

    Devolver "" en vez de adivinar es deliberado: este valor se reenvía a la API
    como parámetro `language` y un valor inválido hace fallar la petición entera
    con un 400. Sin código, Whisper simplemente detecta el idioma él mismo.
    """
    text = (value or "").strip().lower()
    if len(text) == 2 and text.isalpha():
        return text
    return _LANGUAGE_CODES.get(text, "")
