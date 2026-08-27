from __future__ import annotations

import re
from pathlib import Path

from app.models import ContentMode, TranscriptionSegment

_SRT_TIME = re.compile(
    r"(?P<sh>\d{1,2}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{1,2}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})"
)
_LRC_TIME = re.compile(r"\[(?P<m>\d{1,3}):(?P<s>\d{2})(?:[.:](?P<f>\d{1,3}))?\]")
_TRAILING_CLAUSE_PUNCTUATION = re.compile(
    r"[，,。．.!！?？；;：:、…]+(?P<closing>[」』”’）》】〕〉）)\]]*)$"
)


def _seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


class SubtitleParser:
    def parse_srt(self, file_path: str | Path) -> list[TranscriptionSegment]:
        text = Path(file_path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        segments: list[TranscriptionSegment] = []
        for block in re.split(r"\n\s*\n", text.strip()):
            lines = [line.strip() for line in block.splitlines()]
            if not lines:
                continue
            time_index = next((i for i, line in enumerate(lines) if _SRT_TIME.search(line)), None)
            if time_index is None:
                continue
            match = _SRT_TIME.search(lines[time_index])
            assert match is not None
            body = "\n".join(lines[time_index + 1 :]).strip()
            if body:
                groups = match.groupdict()
                segments.append(
                    TranscriptionSegment(
                        len(segments) + 1,
                        _seconds(groups["sh"], groups["sm"], groups["ss"], groups["sms"]),
                        _seconds(groups["eh"], groups["em"], groups["es"], groups["ems"]),
                        body,
                    )
                )
        return segments

    def parse_lrc(self, file_path: str | Path) -> list[TranscriptionSegment]:
        pending: list[tuple[float, str]] = []
        for line in Path(file_path).read_text(encoding="utf-8-sig").splitlines():
            matches = list(_LRC_TIME.finditer(line))
            if not matches:
                continue
            text = _LRC_TIME.sub("", line).strip()
            for match in matches:
                fraction = match.group("f") or "0"
                fraction_seconds = int(fraction) / (10 ** len(fraction))
                pending.append((int(match.group("m")) * 60 + int(match.group("s")) + fraction_seconds, text))
        pending.sort(key=lambda item: item[0])
        return [
            TranscriptionSegment(i + 1, start, pending[i + 1][0] if i + 1 < len(pending) else start + 5, text)
            for i, (start, text) in enumerate(pending)
        ]

    def export_srt(
        self, segments: list[TranscriptionSegment], content_mode: ContentMode, output_path: str | Path
    ) -> str:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        blocks = []
        for i, segment in enumerate(segments, 1):
            blocks.append(f"{i}\n{self._srt_time(segment.start_time)} --> {self._srt_time(segment.end_time)}\n{self._content(segment, content_mode, chr(10))}")
        target.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8-sig")
        return str(target)

    def export_lrc(
        self, segments: list[TranscriptionSegment], content_mode: ContentMode, output_path: str | Path
    ) -> str:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            line
            for segment in segments
            for line in self._lrc_lines(segment, content_mode)
        ]
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8-sig")
        return str(target)

    @classmethod
    def _lrc_lines(cls, segment: TranscriptionSegment, mode: ContentMode) -> list[str]:
        timestamp = cls._lrc_time(segment.start_time)
        if mode is ContentMode.BILINGUAL:
            parts = [segment.text]
            if segment.translated_text:
                parts.append(segment.translated_text)
        elif mode is ContentMode.TARGET_ONLY:
            parts = [segment.translated_text or segment.text]
        else:
            parts = [segment.text]
        return [
            f"{timestamp}{cls._clean_visible_lines(part)}"
            for part in parts
            if part
        ]

    @staticmethod
    def _content(segment: TranscriptionSegment, mode: ContentMode, separator: str) -> str:
        if mode is ContentMode.SOURCE_ONLY:
            parts = (segment.text,)
        elif mode is ContentMode.TARGET_ONLY:
            parts = (segment.translated_text or segment.text,)
        else:
            parts = tuple(part for part in (segment.text, segment.translated_text) if part)
        return separator.join(SubtitleParser._clean_visible_lines(part) for part in parts)

    @staticmethod
    def _clean_visible_lines(value: str) -> str:
        """Remove clause-ending punctuation from each emitted subtitle line."""
        return "\n".join(
            _TRAILING_CLAUSE_PUNCTUATION.sub(r"\g<closing>", line.rstrip())
            for line in value.splitlines()
        )

    @staticmethod
    def _srt_time(value: float) -> str:
        millis = max(0, round(value * 1000))
        hours, rest = divmod(millis, 3_600_000)
        minutes, rest = divmod(rest, 60_000)
        seconds, millis = divmod(rest, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    @staticmethod
    def _lrc_time(value: float) -> str:
        centis = max(0, round(value * 100))
        minutes, rest = divmod(centis, 6000)
        seconds, fraction = divmod(rest, 100)
        return f"[{minutes:02d}:{seconds:02d}.{fraction:02d}]"
