"""
Fábrica de proveedores de IA (RF-047).

Un único punto de decisión, gobernado por la variable de entorno `AI_PROVIDER`.
El valor por defecto — `ollama` — es **gratuito y local**.
"""

from __future__ import annotations

from django.conf import settings

from src.shared.domain.exceptions import ValidationError
from src.shared.infrastructure.logging import get_logger

from ...application.ports.embeddings import EmbeddingsPort
from ...application.ports.llm import LLMPort

logger = get_logger("ai.factory")

SUPPORTED = {"ollama", "openai"}


class AIProviderFactory:
    @staticmethod
    def provider_name() -> str:
        name = (settings.AI_SETTINGS.get("PROVIDER") or "ollama").lower()
        if name not in SUPPORTED:
            raise ValidationError(
                f"Proveedor de IA '{name}' no soportado. Opciones: {', '.join(sorted(SUPPORTED))}."
            )
        return name

    @staticmethod
    def create_llm() -> LLMPort:
        name = AIProviderFactory.provider_name()
        if name == "openai":
            from .openai_provider import OpenAILLM

            logger.info("Proveedor LLM: OpenAI")
            return OpenAILLM()

        from .ollama import OllamaLLM

        logger.info("Proveedor LLM: Ollama (gratuito, local)")
        return OllamaLLM()

    @staticmethod
    def create_embeddings() -> EmbeddingsPort:
        name = AIProviderFactory.provider_name()
        if name == "openai":
            from .openai_provider import OpenAIEmbeddings

            return OpenAIEmbeddings()

        from .ollama import OllamaEmbeddings

        return OllamaEmbeddings()
