"""Reexporta los modelos ORM del módulo AI para el registro de Django."""

from .infrastructure.models import (  # noqa: F401
    AIUsageLog,
    Chapter,
    ChatMessage,
    ChatSession,
    Chunk,
    Concept,
    Faq,
    MessageCitation,
    Transcript,
    TranscriptSegment,
)

__all__ = [
    "AIUsageLog",
    "Chapter",
    "ChatMessage",
    "ChatSession",
    "Chunk",
    "Concept",
    "Faq",
    "MessageCitation",
    "Transcript",
    "TranscriptSegment",
]
