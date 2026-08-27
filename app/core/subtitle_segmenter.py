from __future__ import annotations

import math
import re

from app.models import TranscriptionSegment


class SubtitleSegmenter:
    """Normalize ASR cues into readable, non-overlapping subtitle units."""

    _BOUNDARY = re.compile(r"[。！？!?；;，,、：:]\s*|\s+")

    def __init__(self, max_chars: int = 28, max_duration: float = 6.0, merge_gap_ms: int = 250) -> None:
        self.max_chars = max(8, max_chars)
        self.max_duration = max(1.0, max_duration)
        self.merge_gap = max(0, merge_gap_ms) / 1000

    def resegment(self, segments: list[TranscriptionSegment]) -> list[TranscriptionSegment]:
        merged = self._merge_micro_segments(segments)
        result: list[TranscriptionSegment] = []
        for segment in merged:
            result.extend(self._split_segment(segment))
        for index, segment in enumerate(result, 1):
            segment.index = index
            if index > 1:
                previous = result[index - 2]
                overlap = previous.end_time - segment.start_time
                if 0 < overlap <= 0.5:
                    segment.start_time = previous.end_time
                    segment.end_time = max(segment.start_time, segment.end_time)
        return result

    def _merge_micro_segments(self, segments: list[TranscriptionSegment]) -> list[TranscriptionSegment]:
        merged: list[TranscriptionSegment] = []
        for source in segments:
            current = TranscriptionSegment(0, source.start_time, source.end_time, source.text)
            if merged:
                previous = merged[-1]
                gap = current.start_time - previous.end_time
                short = (previous.end_time - previous.start_time) < 2.5 and (current.end_time - current.start_time) < 1.2
                combined_duration = current.end_time - previous.start_time
                combined_chars = self._length(previous.text) + self._length(current.text)
                if -0.5 <= gap <= self.merge_gap and short and combined_duration <= 4.0 and combined_chars <= self.max_chars:
                    previous.text = self._join(previous.text, current.text)
                    previous.end_time = max(previous.end_time, current.end_time)
                    continue
            merged.append(current)
        return merged

    def _split_segment(self, segment: TranscriptionSegment) -> list[TranscriptionSegment]:
        text = segment.text.strip()
        duration = segment.end_time - segment.start_time
        parts = max(1, math.ceil(self._length(text) / self.max_chars), math.ceil(duration / self.max_duration))
        if parts == 1:
            return [segment]
        chunks = self._balanced_chunks(text, parts)
        cursor = segment.start_time
        output: list[TranscriptionSegment] = []
        for position, chunk in enumerate(chunks):
            end = segment.end_time if position == len(chunks) - 1 else segment.start_time + duration * (position + 1) / len(chunks)
            output.append(TranscriptionSegment(0, cursor, end, chunk))
            cursor = end
        return output

    def _balanced_chunks(self, text: str, count: int) -> list[str]:
        boundaries = [match.end() for match in self._BOUNDARY.finditer(text) if 2 <= match.end() <= len(text) - 2]
        cuts: list[int] = []
        previous = 0
        for part in range(1, count):
            target = round(len(text) * part / count)
            candidates = [value for value in boundaries if value > previous + 2 and value < len(text) - (count - part) * 2]
            nearest = min(candidates, key=lambda value: abs(value - target)) if candidates else target
            tolerance = max(3, round(len(text) / count * 0.3))
            cut = nearest if abs(nearest - target) <= tolerance else target
            cut = max(previous + 1, min(cut, len(text) - (count - part)))
            cuts.append(cut)
            previous = cut
        chunks = []
        start = 0
        for end in [*cuts, len(text)]:
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end
        return chunks or [text]

    @staticmethod
    def _length(text: str) -> int:
        return len(re.sub(r"\s+", "", text))

    @staticmethod
    def _join(left: str, right: str) -> str:
        separator = " " if left[-1:].isascii() and right[:1].isascii() else ""
        return f"{left.rstrip()}{separator}{right.lstrip()}"


__all__ = ["SubtitleSegmenter"]
