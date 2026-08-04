"""
Política de fragmentación (chunking) · lógica de dominio pura.

Reglas (docs/11-diseno-rag.md §3):
- ~800 tokens por fragmento con 15 % de solapamiento.
- Cortar preferentemente en fin de oración.
- No cruzar la frontera de un capítulo.
- Conservar SIEMPRE la ubicación (timestamp para video, página para documento).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")

#: Aproximación robusta y barata para español: ~4 caracteres por token.
CHARS_PER_TOKEN = 4


@dataclass
class SourceBlock:
    """Bloque normalizado que llega desde la transcripción o el extractor."""

    text: str
    order: int
    start_time: float | None = None
    end_time: float | None = None
    page: int | None = None
    heading: str | None = None


@dataclass
class TextChunk:
    index: int
    content: str
    token_count: int
    start_time: float | None = None
    end_time: float | None = None
    page: int | None = None
    heading: str | None = None
    source_orders: list[int] = field(default_factory=list)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


class ChunkingPolicy:
    def __init__(self, *, chunk_size_tokens: int = 800, overlap_tokens: int = 120) -> None:
        if overlap_tokens >= chunk_size_tokens:
            raise ValueError("El solapamiento debe ser menor que el tamaño del fragmento.")
        self.chunk_size = chunk_size_tokens
        self.overlap = overlap_tokens

    def split(self, blocks: list[SourceBlock]) -> list[TextChunk]:
        """Agrupa bloques consecutivos hasta llenar el fragmento."""
        chunks: list[TextChunk] = []
        buffer: list[SourceBlock] = []
        buffer_tokens = 0

        for block in blocks:
            block_tokens = estimate_tokens(block.text)

            # Un bloque enorme (una página densa) se parte por oraciones.
            if block_tokens > self.chunk_size:
                if buffer:
                    chunks.append(self._build(len(chunks), buffer))
                    buffer, buffer_tokens = [], 0
                chunks.extend(self._split_large_block(block, len(chunks)))
                continue

            if buffer_tokens + block_tokens > self.chunk_size and buffer:
                chunks.append(self._build(len(chunks), buffer))
                buffer, buffer_tokens = self._carry_overlap(buffer)

            buffer.append(block)
            buffer_tokens += block_tokens

        if buffer:
            chunks.append(self._build(len(chunks), buffer))

        return [c for c in chunks if c.content.strip()]

    # ── Interno ──────────────────────────────────────────────
    def _carry_overlap(self, buffer: list[SourceBlock]) -> tuple[list[SourceBlock], int]:
        """Arrastra los últimos bloques para mantener continuidad entre fragmentos."""
        carried: list[SourceBlock] = []
        tokens = 0
        for block in reversed(buffer):
            block_tokens = estimate_tokens(block.text)
            if tokens + block_tokens > self.overlap:
                break
            carried.insert(0, block)
            tokens += block_tokens
        return carried, tokens

    def _build(self, index: int, blocks: list[SourceBlock]) -> TextChunk:
        text = " ".join(b.text.strip() for b in blocks if b.text.strip())
        starts = [b.start_time for b in blocks if b.start_time is not None]
        ends = [b.end_time for b in blocks if b.end_time is not None]
        pages = [b.page for b in blocks if b.page is not None]
        headings = [b.heading for b in blocks if b.heading]

        return TextChunk(
            index=index,
            content=text,
            token_count=estimate_tokens(text),
            start_time=min(starts) if starts else None,
            end_time=max(ends) if ends else None,
            page=min(pages) if pages else None,
            heading=headings[0] if headings else None,
            source_orders=[b.order for b in blocks],
        )

    def _split_large_block(self, block: SourceBlock, start_index: int) -> list[TextChunk]:
        """Divide un bloque grande respetando el fin de oración."""
        sentences = [s for s in SENTENCE_END.split(block.text) if s.strip()]
        chunks: list[TextChunk] = []
        current: list[str] = []
        tokens = 0

        def flush() -> None:
            nonlocal current, tokens
            if not current:
                return
            text = " ".join(current).strip()
            chunks.append(
                TextChunk(
                    index=start_index + len(chunks),
                    content=text,
                    token_count=estimate_tokens(text),
                    start_time=block.start_time,
                    end_time=block.end_time,
                    page=block.page,
                    heading=block.heading,
                    source_orders=[block.order],
                )
            )
            current = []
            tokens = 0

        for sentence in sentences:
            sentence_tokens = estimate_tokens(sentence)
            if tokens + sentence_tokens > self.chunk_size and current:
                flush()
            current.append(sentence)
            tokens += sentence_tokens

        flush()
        return chunks
