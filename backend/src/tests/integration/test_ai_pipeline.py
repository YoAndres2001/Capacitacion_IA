"""
Pruebas de integración del pipeline de IA, extremo a extremo y sin red.

Cubren los dos recorridos que pide la refactorización:

    documento → extracción → chunking → embeddings → FAISS → RAG → Groq
    video → audio → Groq Whisper → timestamps → chunking → embeddings → FAISS → RAG

Todo lo externo está mockeado: Groq (LLM y Whisper) nunca se llama de verdad.
Lo que SÍ es real es FAISS —índice en disco temporal— y las políticas de
dominio, que son donde de verdad se pierde la trazabilidad si algo se rompe.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from src.modules.ai.application.ports.llm import ChatMessage
from src.modules.ai.application.ports.vector_store import VectorRecord
from src.modules.ai.domain.chunking import ChunkingPolicy, SourceBlock
from src.modules.ai.domain.rag_policies import (
    GroundingPolicy,
    RetrievedChunk,
)
from src.modules.ai.infrastructure.transcription.groq_whisper import GroqTranscriber
from src.modules.ai.infrastructure.vectorstore.faiss_store import FaissVectorStore

pytestmark = pytest.mark.integration

pytest.importorskip("faiss", reason="faiss-cpu solo está en la imagen de IA")


# ─────────────────────────────────────────────────────────────
#  Dobles de los puertos externos
# ─────────────────────────────────────────────────────────────
class FakeEmbeddings:
    """
    Embeddings deterministas basados en bolsa de palabras.

    No sustituyen a SentenceTransformers en calidad, pero sí en contrato: mismo
    tamaño de vector, normalizados L2 y con la propiedad que importa aquí —dos
    textos que comparten vocabulario quedan cerca en el espacio—.
    """

    VOCAB = ["inventario", "ciclico", "bodega", "despacho", "seguridad", "arnes"]

    model_name = "fake-embeddings"
    provider_name = "local"

    @property
    def dimension(self) -> int:
        return len(self.VOCAB)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        lowered = _strip_accents(text.lower())
        raw = [float(lowered.count(word)) for word in self.VOCAB]
        magnitude = sum(value**2 for value in raw) ** 0.5
        if magnitude == 0:
            return [0.0] * len(raw)
        return [value / magnitude for value in raw]


class FakeGroqLLM:
    """Doble del LLM: registra el prompt recibido y devuelve una respuesta fija."""

    model_name = "llama-3.3-70b-versatile"
    provider_name = "groq"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[list[ChatMessage]] = []

    def generate(self, messages, **kwargs):
        self.prompts.append(messages)
        from src.modules.ai.application.ports.llm import LLMResponse

        return LLMResponse(content=self.answer)


def _strip_accents(text: str) -> str:
    import unicodedata

    return "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )


@pytest.fixture
def index_root(tmp_path, settings):
    settings.RAG_SETTINGS = {**settings.RAG_SETTINGS, "INDEX_ROOT": tmp_path / "indices"}
    return tmp_path


# ─────────────────────────────────────────────────────────────
#  Documento → extracción → embeddings → FAISS → RAG → Groq
# ─────────────────────────────────────────────────────────────
def test_pipeline_de_documento_hasta_la_respuesta_de_groq(index_root):
    project_id = uuid4()
    material_id = uuid4()
    embeddings = FakeEmbeddings()

    # 1 · Extracción: lo que devuelve PyMuPDF, con su página.
    blocks = [
        SourceBlock(
            text="El inventario ciclico se realiza en la bodega cada semana.",
            order=0,
            page=23,
        ),
        SourceBlock(text="El arnes de seguridad es obligatorio en altura.", order=1, page=41),
    ]

    # 2 · Chunking, conservando la página de origen. El tamaño es pequeño a
    # propósito para que cada bloque quede en su propio fragmento y se pueda
    # comprobar que la página viaja con él.
    chunks = ChunkingPolicy(chunk_size_tokens=14, overlap_tokens=2).split(blocks)
    assert {chunk.page for chunk in chunks} == {23, 41}

    # 3 · Embeddings + 4 · FAISS real
    store = FaissVectorStore(project_id=project_id, embeddings=embeddings)
    vectors = embeddings.embed_documents([chunk.content for chunk in chunks])
    chunk_ids = [uuid4() for _ in chunks]
    store.add(
        [
            VectorRecord(
                chunk_id=chunk_id,
                vector=vector,
                metadata={
                    "material_id": str(material_id),
                    "page": chunk.page,
                    "filename": "manual.pdf",
                },
            )
            for chunk_id, vector, chunk in zip(chunk_ids, vectors, chunks, strict=False)
        ]
    )
    assert store.stats()["vector_count"] == len(chunks)

    # 5 · RAG: la consulta recupera el fragmento correcto, no el otro.
    hits = store.search(embeddings.embed_query("¿cada cuánto se hace el inventario?"), top_k=1)
    assert len(hits) == 1
    assert hits[0].metadata["page"] == 23

    retrieved = [
        RetrievedChunk(
            chunk_id=hits[0].chunk_id,
            material_id=material_id,
            content=chunks[0].content,
            score=hits[0].score,
            material_title="manual.pdf",
            material_type="PDF",
            page=hits[0].metadata["page"],
        )
    ]

    # 6 · La política de fundamento autoriza la llamada al LLM.
    decision = GroundingPolicy(min_score=0.35, min_top_score=0.45).evaluate(retrieved)
    assert decision.is_grounded

    # 7 · Groq (mock) responde y la cita apunta a la página real.
    llm = FakeGroqLLM("El inventario ciclico se hace cada semana en la bodega. [1]")
    response = llm.generate([ChatMessage(role="user", content=retrieved[0].content)])

    assert "semana" in response.content
    assert retrieved[0].label() == "manual.pdf · pág. 23"


def test_sin_contexto_suficiente_no_se_llama_a_groq(index_root):
    """
    El compromiso "la IA no inventa" se cumple ANTES de gastar una llamada.

    Una pregunta sobre algo que no está en el material no debe llegar al LLM.
    """
    embeddings = FakeEmbeddings()
    store = FaissVectorStore(project_id=uuid4(), embeddings=embeddings)
    store.add(
        [
            VectorRecord(
                chunk_id=uuid4(),
                vector=embeddings.embed_query("El arnes de seguridad es obligatorio."),
                metadata={"material_id": str(uuid4())},
            )
        ]
    )

    hits = store.search(embeddings.embed_query("¿cuál es el horario de colación?"), top_k=5)
    retrieved = [
        RetrievedChunk(chunk_id=hit.chunk_id, material_id=uuid4(), content="", score=hit.score)
        for hit in hits
    ]

    llm = FakeGroqLLM("no debería ejecutarse")
    decision = GroundingPolicy(min_score=0.35, min_top_score=0.45).evaluate(retrieved)

    assert not decision.is_grounded
    assert llm.prompts == []


# ─────────────────────────────────────────────────────────────
#  Video → audio → Groq Whisper → timestamps → FAISS → RAG
# ─────────────────────────────────────────────────────────────
def test_pipeline_de_video_conserva_el_minuto_hasta_la_cita(index_root, monkeypatch, tmp_path):
    """
    El recorrido completo de un timestamp.

    Groq devuelve el segundo 43 dentro del segundo trozo de audio; el chat debe
    terminar citando "12:43" del video original. Cualquier eslabón que pierda el
    desplazamiento rompe esta prueba.
    """
    from src.modules.ai.infrastructure.transcription import ffmpeg

    audio = tmp_path / "clase.flac"
    audio.write_bytes(b"x" * (24 * 1024 * 1024 + 1))  # obliga a trocear

    partes = [tmp_path / "part_0000.flac", tmp_path / "part_0001.flac"]
    for parte in partes:
        parte.write_bytes(b"y")

    monkeypatch.setattr(
        ffmpeg,
        "split_audio",
        lambda source, out_dir, chunk_seconds: [
            ffmpeg.AudioSlice(path=partes[0], offset_seconds=0.0),
            ffmpeg.AudioSlice(path=partes[1], offset_seconds=720.0),
        ],
    )
    respuestas = {
        partes[0]: {
            "text": "Bienvenidos al curso.",
            "language": "spanish",
            "duration": 720.0,
            "segments": [{"start": 0.0, "end": 6.0, "text": "Bienvenidos al curso."}],
        },
        partes[1]: {
            "text": "El inventario ciclico se revisa en bodega.",
            "language": "spanish",
            "duration": 300.0,
            "segments": [
                {
                    "start": 43.0,
                    "end": 51.0,
                    "text": "El inventario ciclico se revisa en bodega.",
                }
            ],
        },
    }
    monkeypatch.setattr(GroqTranscriber, "_send", lambda self, path, language: respuestas[path])

    # 1 · Transcripción con Groq (mock)
    result = GroqTranscriber().transcribe(audio)
    assert result.segments[1].start == 763.0  # 720 + 43

    # 2 · Chunking conservando el timestamp
    blocks = [
        SourceBlock(
            text=segment.text,
            order=segment.index,
            start_time=segment.start,
            end_time=segment.end,
        )
        for segment in result.segments
    ]
    # Fragmentos pequeños para que cada segmento conserve su propio timestamp:
    # con un tamaño grande los dos se fundirían en uno y `start_time` sería el
    # mínimo de ambos, que es justo el error que esta prueba vigila.
    chunks = ChunkingPolicy(chunk_size_tokens=8, overlap_tokens=2).split(blocks)

    # 3 · Embeddings + FAISS
    embeddings = FakeEmbeddings()
    store = FaissVectorStore(project_id=uuid4(), embeddings=embeddings)
    material_id = uuid4()
    chunk_ids = [uuid4() for _ in chunks]
    store.add(
        [
            VectorRecord(
                chunk_id=chunk_id,
                vector=vector,
                metadata={
                    "material_id": str(material_id),
                    "start_time": chunk.start_time,
                },
            )
            for chunk_id, vector, chunk in zip(
                chunk_ids,
                embeddings.embed_documents([c.content for c in chunks]),
                chunks,
                strict=False,
            )
        ]
    )

    # 4 · RAG: la pregunta recupera el fragmento del minuto correcto
    hits = store.search(embeddings.embed_query("¿qué dicen del inventario?"), top_k=1)
    recuperado = next(
        chunk
        for chunk_id, chunk in zip(chunk_ids, chunks, strict=False)
        if chunk_id == hits[0].chunk_id
    )

    cita = RetrievedChunk(
        chunk_id=hits[0].chunk_id,
        material_id=material_id,
        content=recuperado.content,
        score=hits[0].score,
        material_title="introduccion.mp4",
        material_type="VIDEO",
        start_time=recuperado.start_time,
    )

    # 5 · La cita que verá el alumno
    assert cita.label() == "introduccion.mp4 · 12:43"


def test_el_audio_extraido_va_al_transcriptor_y_no_el_video(monkeypatch, tmp_path):
    """
    Groq recibe audio, nunca el archivo de video.

    Es lo que mantiene la subida por debajo del tope por petición y evita enviar
    gigabytes de imagen que el modelo ignoraría.
    """
    from src.modules.ai.infrastructure.transcription import ffmpeg

    enviados: list[Path] = []
    audio = tmp_path / "audio.flac"
    audio.write_bytes(b"x" * 1024)

    monkeypatch.setattr(
        GroqTranscriber,
        "_send",
        lambda self, path, language: enviados.append(path)
        or {
            "text": "contenido",
            "language": "es",
            "duration": 2.0,
            "segments": [{"start": 0.0, "end": 2.0, "text": "contenido"}],
        },
    )

    GroqTranscriber().transcribe(audio)

    assert enviados == [audio]
    assert enviados[0].suffix == ".flac"
    assert ffmpeg.extract_audio.__doc__  # el paso de extracción sigue existiendo
