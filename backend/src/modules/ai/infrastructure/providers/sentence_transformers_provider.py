"""
Embeddings LOCALES con SentenceTransformers.

Groq no ofrece API de embeddings y no queremos un segundo proveedor externo, así
que el vector se calcula dentro del propio worker: **ninguna llamada de red**, el
contenido de la empresa no sale de su infraestructura y no hay cuota que agotar.

El modelo por defecto es multilingüe y está entrenado para búsqueda asimétrica
(pregunta corta contra pasaje largo), que es lo que hace el RAG. Se carga una
sola vez por proceso (`_model_cache`): la carga tarda decenas de segundos, la
inferencia milisegundos.
"""

from __future__ import annotations

import threading

from django.conf import settings

from src.shared.domain.exceptions import AIProviderUnavailable
from src.shared.infrastructure.logging import get_logger

from ...application.ports.embeddings import EmbeddingsPort
from .parsing import normalize

logger = get_logger("ai.embeddings")

_model_lock = threading.Lock()
_model_cache: dict[str, object] = {}


def _config() -> dict:
    return settings.EMBEDDING_SETTINGS


class SentenceTransformerEmbeddings(EmbeddingsPort):
    """
    Adaptador local del `EmbeddingsPort`.

    La interfaz del puerto no cambia respecto de la implementación anterior: el
    almacén FAISS y el pipeline de ingesta siguen funcionando igual.
    """

    def __init__(self, model: str | None = None, device: str | None = None) -> None:
        config = _config()
        self._model_id = model or config["MODEL"]
        self._device = device or config["DEVICE"]
        self._batch_size = int(config.get("BATCH_SIZE", 32))
        # E5 y familia distinguen la consulta del pasaje mediante un prefijo en
        # el propio texto. Es la razón por la que el puerto separa
        # `embed_query` de `embed_documents`.
        self._query_prefix = config.get("QUERY_PREFIX", "")
        self._passage_prefix = config.get("PASSAGE_PREFIX", "")
        self._dimension = 0

    @property
    def model_name(self) -> str:
        return self._model_id

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def dimension(self) -> int:
        """
        Dimensión del vector.

        Se pregunta al propio modelo en vez de embeber un texto de prueba: es
        instantáneo y evita una inferencia inútil en cada arranque.
        """
        if not self._dimension:
            model = self._load_model()
            reported = model.get_sentence_embedding_dimension()  # type: ignore[attr-defined]
            self._dimension = int(reported or len(self.embed_query("dimensión")))
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._encode([self._passage_prefix + text for text in texts])
        if vectors:
            self._dimension = len(vectors[0])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self._encode([self._query_prefix + text])
        return vectors[0] if vectors else []

    # ── Interno ──────────────────────────────────────────────
    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        try:
            raw = model.encode(  # type: ignore[attr-defined]
                texts,
                batch_size=self._batch_size,
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=False,
            )
        except Exception as exc:  # pragma: no cover - depende del modelo
            raise AIProviderUnavailable(
                f"Fallo al generar embeddings locales con '{self._model_id}': {exc}"
            ) from exc

        # La normalización L2 se hace aquí (y no con `normalize_embeddings=True`)
        # para que el vector salga del adaptador con exactamente el mismo
        # tratamiento que espera el índice FAISS (`IndexFlatIP` = coseno).
        return [normalize([float(value) for value in vector]) for vector in raw]

    def _load_model(self):
        """Carga perezosa y cacheada: el modelo se reutiliza entre tareas del worker."""
        key = f"{self._model_id}:{self._device}"
        cached = _model_cache.get(key)
        if cached is not None:
            return cached

        with _model_lock:
            cached = _model_cache.get(key)
            if cached is not None:
                return cached

            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover
                raise AIProviderUnavailable(
                    "`sentence-transformers` no está instalado en este contenedor. "
                    "Los embeddings deben calcularse en las colas `ingest` o `ai`."
                ) from exc

            logger.info(
                "Cargando modelo de embeddings local",
                extra={"model": self._model_id, "device": self._device},
            )
            try:
                model = SentenceTransformer(self._model_id, device=self._device)
            except Exception as exc:
                raise AIProviderUnavailable(
                    f"No se pudo cargar el modelo de embeddings '{self._model_id}': {exc}. "
                    "Revise EMBEDDING_MODEL."
                ) from exc

            _model_cache[key] = model
            return model
