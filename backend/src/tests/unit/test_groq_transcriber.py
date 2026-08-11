"""
Transcripción con Groq Whisper · lo que se rompe en silencio.

El riesgo real de este adaptador no es que falle la llamada —eso se ve—, sino
que los timestamps salgan mal: el chat citaría "minuto 3:20" cuando la frase
está en el 13:20 y nadie lo notaría hasta que un alumno lo reportara.

Groq se mockea siempre: ninguna prueba consume la API real.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from src.modules.ai.infrastructure.transcription import ffmpeg, groq_whisper
from src.modules.ai.infrastructure.transcription.groq_whisper import (
    GroqTranscriber,
    NoSpeechDetected,
    _normalize_language,
    _segments_from,
)

pytestmark = pytest.mark.unit


def _payload(segments, *, language="spanish", duration=0.0):
    return {
        "text": " ".join(text for _, _, text in segments),
        "language": language,
        "duration": duration,
        "segments": [{"start": start, "end": end, "text": text} for start, end, text in segments],
    }


# ── Conversión de segmentos ──────────────────────────────────
def test_los_timestamps_se_desplazan_con_el_offset_del_trozo():
    """Un trozo que empieza en el minuto 10 debe reportar 600 s, no 0 s."""
    segments = _segments_from(_payload([(0.0, 8.4, "Hola")]), offset=600.0)

    assert (segments[0].start, segments[0].end) == (600.0, 608.4)


def test_sin_offset_los_timestamps_quedan_intactos():
    segments = _segments_from(_payload([(1.25, 3.5, "Inventario cíclico")]), offset=0.0)

    assert (segments[0].start, segments[0].end) == (1.25, 3.5)


def test_se_descartan_los_segmentos_vacios():
    segments = _segments_from(_payload([(0.0, 1.0, "  "), (1.0, 2.0, "válido")]), offset=0.0)

    assert [segment.text for segment in segments] == ["válido"]


def test_si_no_hay_segmentos_se_rescata_el_texto_completo():
    """Preferible una cita imprecisa a perder el material para el RAG."""
    segments = _segments_from(
        {"text": "Texto sin segmentar", "duration": 12.0, "segments": []}, offset=30.0
    )

    assert len(segments) == 1
    assert (segments[0].start, segments[0].end) == (30.0, 42.0)


# ── Idioma ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("recibido", "esperado"),
    [
        ("spanish", "es"),
        ("Spanish", "es"),
        ("english", "en"),
        ("es", "es"),
        ("", ""),
        # Sin traducción conocida se devuelve vacío en vez de adivinar: este
        # valor se reenvía a la API y uno inválido tumba la petición entera.
        ("klingon", ""),
    ],
)
def test_el_idioma_se_normaliza_a_codigo_iso(recibido, esperado):
    assert _normalize_language(recibido) == esperado


def test_al_trocear_se_reenvia_el_idioma_como_codigo_iso(monkeypatch, tmp_path):
    """
    Bug medido contra la API real: Groq devuelve `"language": "Spanish"` pero su
    parámetro `language` solo acepta el código ISO. Reenviar el nombre tal cual
    hacía fallar con 400 *todos los trozos a partir del segundo*, es decir, la
    transcripción de cualquier video largo.
    """
    audio = tmp_path / "largo.flac"
    audio.write_bytes(b"x" * (groq_whisper.MAX_UPLOAD_BYTES + 1))

    partes = [tmp_path / "part_0000.flac", tmp_path / "part_0001.flac"]
    for parte in partes:
        parte.write_bytes(b"y")

    monkeypatch.setattr(
        ffmpeg,
        "split_audio",
        lambda source, out_dir, chunk_seconds: [
            ffmpeg.AudioSlice(path=partes[0], offset_seconds=0.0),
            ffmpeg.AudioSlice(path=partes[1], offset_seconds=30.0),
        ],
    )

    idiomas_enviados: list[str | None] = []

    def capturar(self, path, language):
        idiomas_enviados.append(language)
        # Groq responde con el NOMBRE del idioma, no con el código.
        return _payload([(0.0, 5.0, "texto")], language="Spanish", duration=30.0)

    monkeypatch.setattr(GroqTranscriber, "_send", capturar)
    result = GroqTranscriber().transcribe(audio)

    # Primer trozo sin idioma (que lo detecte Whisper); a partir del segundo, el
    # detectado pero traducido a ISO.
    assert idiomas_enviados == [None, "es"]
    assert result.language == "es"


# ── Pipeline completo del adaptador ──────────────────────────
def test_un_audio_pequeno_se_envia_en_una_sola_peticion(monkeypatch, tmp_path):
    audio = tmp_path / "audio.flac"
    audio.write_bytes(b"x" * 1024)

    enviados: list[Path] = []

    def fake_send(self, path, language):
        enviados.append(path)
        return _payload([(0.0, 5.0, "Una sola parte")], duration=5.0)

    monkeypatch.setattr(GroqTranscriber, "_send", fake_send)
    result = GroqTranscriber(model="whisper-large-v3").transcribe(audio)

    assert enviados == [audio]
    assert result.language == "es"
    assert result.duration == 5.0
    assert result.model == "groq-whisper-large-v3"


def test_un_audio_grande_se_divide_y_los_timestamps_siguen_siendo_globales(monkeypatch, tmp_path):
    """
    El caso que justifica el troceo: el segundo trozo no puede volver a 0:00.

    Se simulan dos partes de 600 s. La frase que Groq sitúa en el segundo 12 de
    la segunda parte tiene que quedar en el 612 del video completo.
    """
    audio = tmp_path / "largo.flac"
    audio.write_bytes(b"x" * (groq_whisper.MAX_UPLOAD_BYTES + 1))

    partes = [tmp_path / "part_0000.flac", tmp_path / "part_0001.flac"]
    for parte in partes:
        parte.write_bytes(b"y")

    monkeypatch.setattr(
        ffmpeg,
        "split_audio",
        lambda source, out_dir, chunk_seconds: [
            ffmpeg.AudioSlice(path=partes[0], offset_seconds=0.0),
            ffmpeg.AudioSlice(path=partes[1], offset_seconds=600.0),
        ],
    )

    respuestas = {
        partes[0]: _payload([(0.0, 4.0, "Introducción")], duration=600.0),
        partes[1]: _payload([(12.0, 20.0, "Inventario cíclico")], duration=600.0),
    }
    monkeypatch.setattr(GroqTranscriber, "_send", lambda self, path, language: respuestas[path])

    progreso: list[int] = []
    result = GroqTranscriber().transcribe(audio, on_progress=progreso.append)

    assert [(s.start, s.end) for s in result.segments] == [(0.0, 4.0), (612.0, 620.0)]
    # Los índices se renumeran de forma global: cada trozo los devuelve desde 0.
    assert [s.index for s in result.segments] == [0, 1]
    assert result.duration == 1200.0
    assert progreso == [50, 99]


def test_un_audio_sin_voz_se_reporta_como_tal(monkeypatch, tmp_path):
    audio = tmp_path / "silencio.flac"
    audio.write_bytes(b"x")

    monkeypatch.setattr(
        GroqTranscriber,
        "_send",
        lambda self, path, language: {"text": "", "segments": [], "duration": 3.0},
    )

    with pytest.raises(NoSpeechDetected):
        GroqTranscriber().transcribe(audio)


def test_un_limite_de_uso_se_reintenta_y_termina_bien(monkeypatch, tmp_path):
    """
    El 429 de Groq no debe perder la transcripción.

    Se fuerza un fallo en el primer intento y se comprueba que la política de
    reintentos del adaptador lo absorbe. La espera se anula para que la prueba
    no dure lo que dice `Retry-After`.
    """
    audio = tmp_path / "audio.flac"
    audio.write_bytes(b"x")

    intentos = {"n": 0}

    def flaky(self, path, language):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise requests.ConnectionError("conexión interrumpida")
        return _payload([(0.0, 2.0, "Segundo intento")], duration=2.0)

    # `_send` ya viene decorado; se re-aplica el decorador sobre el doble para
    # ejercitar la política real, con espera cero.
    from tenacity import retry, retry_if_exception_type, stop_after_attempt

    monkeypatch.setattr(
        GroqTranscriber,
        "_send",
        retry(
            stop=stop_after_attempt(3),
            wait=lambda _: 0,
            retry=retry_if_exception_type(requests.RequestException),
            reraise=True,
        )(flaky),
    )

    result = GroqTranscriber().transcribe(audio)

    assert intentos["n"] == 2
    assert result.full_text == "Segundo intento"
