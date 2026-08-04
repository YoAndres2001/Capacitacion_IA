"""Selección del extractor adecuado según el tipo de material."""

from __future__ import annotations

from src.shared.domain.exceptions import InvalidFileType

from ...application.ports.extractor import DocumentExtractorPort
from .extractors import DocxExtractor, PdfExtractor, PlainTextExtractor, PptxExtractor

EXTRACTORS: list[DocumentExtractorPort] = [
    PdfExtractor(),
    DocxExtractor(),
    PptxExtractor(),
    PlainTextExtractor(),
]


class ExtractorFactory:
    @staticmethod
    def for_type(material_type: str) -> DocumentExtractorPort:
        for extractor in EXTRACTORS:
            if extractor.supports(material_type):
                return extractor
        raise InvalidFileType(f"No hay extractor disponible para el tipo '{material_type}'.")
