"""
Fábrica de adaptadores de IA (RF-047).

Ya no hay selección dinámica de proveedor: **Groq es el único servicio externo**
de la plataforma y los embeddings se calculan en local. La fábrica se mantiene
porque es el punto donde los puertos (`LLMPort`, `EmbeddingsPort`) se atan a su
implementación y donde se registra qué modelos quedaron en uso.

Configuración necesaria: `GROQ_API_KEY`, `GROQ_LLM_MODEL` y `EMBEDDING_MODEL`.
"""

from __future__ import annotations

from src.shared.infrastructure.logging import get_logger

from ...application.ports.embeddings import EmbeddingsPort
from ...application.ports.llm import LLMPort

logger = get_logger("ai.factory")


class AIProviderFactory:
    @staticmethod
    def create_llm() -> LLMPort:
        from .groq_provider import GroqLLM

        llm = GroqLLM()
        logger.info(f"LLM: Groq ({llm.model_name})")
        return llm

    @staticmethod
    def create_embeddings() -> EmbeddingsPort:
        from .sentence_transformers_provider import SentenceTransformerEmbeddings

        embeddings = SentenceTransformerEmbeddings()
        logger.info(f"Embeddings: SentenceTransformers local ({embeddings.model_name})")
        return embeddings
