"""Puerto de extracción de contenido de documentos."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ContentBlock:
    """
    Unidad normalizada de contenido.

    Video y documento producen la misma estructura, de modo que el chunking,
    los embeddings y el análisis son idénticos para ambos (docs §13.2).
    """

    text: str
    order: int
    start_time: float | None = None
    end_time: float | None = None
    page: int | None = None
    heading: str | None = None


@dataclass
class ExtractionResult:
    blocks: list[ContentBlock]
    page_count: int = 0
    language: str = ""
    used_ocr: bool = False

    @property
    def full_text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)


class DocumentExtractorPort(ABC):
    @abstractmethod
    def supports(self, material_type: str) -> bool: ...

    @abstractmethod
    def extract(self, path: Path) -> ExtractionResult: ...
