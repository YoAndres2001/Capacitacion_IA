"""
Embeddings locales · el contrato que espera FAISS.

El índice usa `IndexFlatIP`, de modo que el producto interno solo equivale a la
similitud coseno si los vectores llegan normalizados L2. Si el adaptador dejara
de normalizar, la búsqueda seguiría "funcionando" pero devolvería resultados
peores sin ningún error visible: por eso se fija aquí.

El modelo se mockea: la prueba no descarga pesos ni llama a ningún servicio.
"""

from __future__ import annotations

import pytest

from src.modules.ai.infrastructure.providers import sentence_transformers_provider as stp
from src.modules.ai.infrastructure.providers.sentence_transformers_provider import (
    SentenceTransformerEmbeddings,
)

pytestmark = pytest.mark.unit


class _FakeModel:
    """Devuelve vectores deterministas y sin normalizar."""

    def __init__(self, vectors: list[list[float]], dimension: int = 3) -> None:
        self._vectors = vectors
        self._dimension = dimension
        self.calls: list[tuple[int, int]] = []

    def encode(self, texts, *, batch_size, **kwargs):
        self.calls.append((len(texts), batch_size))
        return [self._vectors[index % len(self._vectors)] for index in range(len(texts))]

    def get_sentence_embedding_dimension(self) -> int:
        return self._dimension


@pytest.fixture(autouse=True)
def _clear_model_cache():
    stp._model_cache.clear()
    yield
    stp._model_cache.clear()


def _with_model(monkeypatch, model) -> SentenceTransformerEmbeddings:
    embeddings = SentenceTransformerEmbeddings(model="modelo-de-prueba", device="cpu")
    monkeypatch.setattr(embeddings, "_load_model", lambda: model)
    return embeddings


def test_los_vectores_salen_normalizados_l2(monkeypatch):
    embeddings = _with_model(monkeypatch, _FakeModel([[3.0, 4.0, 0.0]]))

    vector = embeddings.embed_query("inventario")

    assert vector == pytest.approx([0.6, 0.8, 0.0])
    assert sum(component**2 for component in vector) == pytest.approx(1.0)


def test_un_vector_nulo_no_revienta_la_division(monkeypatch):
    """Un texto vacío puede producir el vector cero; no debe lanzar ZeroDivisionError."""
    embeddings = _with_model(monkeypatch, _FakeModel([[0.0, 0.0, 0.0]]))

    assert embeddings.embed_query("") == [0.0, 0.0, 0.0]


def test_una_lista_vacia_no_llama_al_modelo(monkeypatch):
    model = _FakeModel([[1.0, 0.0, 0.0]])
    embeddings = _with_model(monkeypatch, model)

    assert embeddings.embed_documents([]) == []
    assert model.calls == []


def test_los_documentos_se_procesan_por_lotes(monkeypatch):
    """El tamaño de lote configurado llega al modelo: es la palanca de memoria."""
    model = _FakeModel([[1.0, 0.0, 0.0]])
    embeddings = _with_model(monkeypatch, model)
    embeddings._batch_size = 8

    vectors = embeddings.embed_documents(["a", "b", "c"])

    assert len(vectors) == 3
    assert model.calls == [(3, 8)]


def test_la_dimension_se_pregunta_al_modelo_sin_inferir(monkeypatch):
    """Preguntarla evita una inferencia inútil en cada arranque del worker."""
    model = _FakeModel([[1.0, 0.0, 0.0]], dimension=384)
    embeddings = _with_model(monkeypatch, model)

    assert embeddings.dimension == 384
    assert model.calls == []


def test_el_proveedor_se_identifica_como_local(monkeypatch):
    """`usage.estimate_cost` lo usa para no cobrar tokens que nunca salieron."""
    embeddings = _with_model(monkeypatch, _FakeModel([[1.0, 0.0, 0.0]]))

    assert embeddings.provider_name == "local"
