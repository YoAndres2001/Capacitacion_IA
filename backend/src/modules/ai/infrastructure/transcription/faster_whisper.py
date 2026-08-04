"""
Transcripción con `faster-whisper` · **gratuita y local**.

Se eligió sobre `openai-whisper` por ser ~4× más rápido en CPU y usar bastante
menos memoria (ADR-05). El modelo se carga una sola vez por proceso worker.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from django.conf import settings

from src.shared.domain.exceptions import DomainError
from src.shared.infrastructure.logging import get_logger

from ...application.ports.transcriber import (
    TranscriberPort,
    TranscriptionResult,
    TranscriptSegment,
)

logger = get_logger("ai.whisper")

_model_lock = threading.Lock()
_model_cache: dict[str, object] = {}


class TranscriptionFailed(DomainError):
    code = "TRANSCRIPTION_FAILED"
    default_message = "No se pudo transcribir el audio."


class NoSpeechDetected(DomainError):
    code = "NO_SPEECH_DETECTED"
    default_message = "No se detectó voz en el audio."


class FasterWhisperTranscriber(TranscriberPort):
    def __init__(self, model_size: str | None = None) -> None:
        config = settings.WHISPER_SETTINGS
        self._model_size = model_size or config["MODEL"]
        self._device = config["DEVICE"]
        self._compute_type = config["COMPUTE_TYPE"]
        self._beam_size = config["BEAM_SIZE"]

    @property
    def model_name(self) -> str:
        return f"faster-whisper-{self._model_size}"

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> TranscriptionResult:
        model = self._load_model()

        try:
            segments_iter, info = model.transcribe(  # type: ignore[attr-defined]
                str(audio_path),
                language=language,
                beam_size=self._beam_size,
                vad_filter=True,  # descarta silencios: más rápido y menos alucinación
                vad_parameters={"min_silence_duration_ms": 500},
                condition_on_previous_text=False,
            )
        except Exception as exc:  # pragma: no cover - depende del modelo
            raise TranscriptionFailed(str(exc)) from exc

        total_duration = float(getattr(info, "duration", 0) or 0)
        segments: list[TranscriptSegment] = []

        for index, segment in enumerate(segments_iter):
            text = (segment.text or "").strip()
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    index=index,
                    start=round(float(segment.start), 2),
                    end=round(float(segment.end), 2),
                    text=text,
                )
            )
            if on_progress and total_duration > 0 and index % 20 == 0:
                on_progress(min(99, int(float(segment.end) / total_duration * 100)))

        if not segments:
            raise NoSpeechDetected

        return TranscriptionResult(
            language=getattr(info, "language", "") or "es",
            segments=segments,
            duration=total_duration or (segments[-1].end if segments else 0.0),
            model=self.model_name,
            confidence=round(float(getattr(info, "language_probability", 0) or 0), 3),
        )

    # ── Interno ──────────────────────────────────────────────
    def _load_model(self):
        """Carga perezosa y cacheada: el modelo se reutiliza entre tareas del worker."""
        key = f"{self._model_size}:{self._device}:{self._compute_type}"
        if key in _model_cache:
            return _model_cache[key]

        with _model_lock:
            if key in _model_cache:
                return _model_cache[key]
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover
                raise TranscriptionFailed(
                    "`faster-whisper` no está instalado en este contenedor. "
                    "La transcripción debe ejecutarse en la cola `ingest`."
                ) from exc

            logger.info(
                "Cargando modelo Whisper",
                extra={"model": self._model_size, "device": self._device},
            )
            _model_cache[key] = WhisperModel(
                self._model_size, device=self._device, compute_type=self._compute_type
            )
            return _model_cache[key]
