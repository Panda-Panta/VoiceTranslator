from pathlib import Path

import pytest

from app.core.file_handler import FileHandler, UnsupportedFileTypeError
from app.models import FileType


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("voice.WAV", FileType.AUDIO),
        ("movie.mkv", FileType.VIDEO),
        ("captions.srt", FileType.SUBTITLE),
        ("song.lrc", FileType.LYRICS),
    ],
)
def test_detect_type_is_case_insensitive(name: str, expected: FileType) -> None:
    assert FileHandler().detect_type(name) is expected


def test_unknown_type_is_rejected() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        FileHandler().detect_type(Path("notes.txt"))


def test_text_timeline_files_skip_transcription() -> None:
    handler = FileHandler()
    assert not handler.needs_transcription(FileType.SUBTITLE)
    assert not handler.needs_transcription(FileType.LYRICS)
    assert handler.needs_transcription(FileType.AUDIO)
