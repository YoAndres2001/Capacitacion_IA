"""Puerto de transcripción de audio/video."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class TranscriptSegment:
    index: int
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    language: str
    segments: list[TranscriptSegment] = field(default_factory=list)
    duration: float = 0.0
    model: str = ""
    confidence: float = 0.0

    @property
    def full_text(self) -> str:
        return " ".join(segment.text.strip() for segment in self.segments).strip()


class TranscriberPort(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> TranscriptionResult: ...
