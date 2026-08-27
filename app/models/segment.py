from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TranscriptionSegment:
    index: int
    start_time: float
    end_time: float
    text: str
    translated_text: str = ""

    def __post_init__(self) -> None:
        self.start_time = max(0.0, float(self.start_time))
        self.end_time = max(self.start_time, float(self.end_time))
        self.text = self.text.strip()
        self.translated_text = self.translated_text.strip()
