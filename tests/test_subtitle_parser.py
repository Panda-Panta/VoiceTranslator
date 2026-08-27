from pathlib import Path

from app.core.subtitle_parser import SubtitleParser
from app.models import ContentMode, TranscriptionSegment


def test_parse_and_export_srt(tmp_path: Path) -> None:
    source = tmp_path / "input.srt"
    source.write_text(
        "1\n00:00:01,250 --> 00:00:03,500\nHello\n\n2\n00:00:04,000 --> 00:00:05,000\nWorld\n",
        encoding="utf-8",
    )
    parser = SubtitleParser()
    segments = parser.parse_srt(source)
    assert [(s.start_time, s.end_time, s.text) for s in segments] == [
        (1.25, 3.5, "Hello"),
        (4.0, 5.0, "World"),
    ]
    segments[0].translated_text = "你好"
    segments[1].translated_text = "世界"
    target = tmp_path / "output.srt"
    parser.export_srt(segments, ContentMode.BILINGUAL, target)
    result = target.read_text(encoding="utf-8-sig")
    assert "Hello\n你好" in result
    assert "00:00:01,250 --> 00:00:03,500" in result


def test_lrc_multiple_timestamps_and_bilingual_export(tmp_path: Path) -> None:
    source = tmp_path / "input.lrc"
    source.write_text("[00:01.20][00:03.50]Line\n[00:06.00]End\n", encoding="utf-8")
    parser = SubtitleParser()
    segments = parser.parse_lrc(source)
    assert [s.start_time for s in segments] == [1.2, 3.5, 6.0]
    segments[0].translated_text = "行"
    target = tmp_path / "output.lrc"
    parser.export_lrc(segments, ContentMode.BILINGUAL, target)
    result = target.read_text(encoding="utf-8-sig")
    assert "[00:01.20]Line\n[00:01.20]行\n" in result
    assert " / " not in result


def test_target_only_falls_back_to_source_when_not_translated(tmp_path: Path) -> None:
    target = tmp_path / "plain.srt"
    SubtitleParser().export_srt(
        [TranscriptionSegment(1, 0, 1, "source")], ContentMode.TARGET_ONLY, target
    )
    assert "source" in target.read_text(encoding="utf-8-sig")


def test_export_removes_clause_punctuation_from_each_visible_line(tmp_path: Path) -> None:
    target = tmp_path / "clean.srt"
    SubtitleParser().export_srt(
        [TranscriptionSegment(1, 0, 1, "你好，世界。\n「走吧！」", "Hello, world!")],
        ContentMode.BILINGUAL,
        target,
    )

    result = target.read_text(encoding="utf-8-sig")
    assert "你好，世界\n「走吧」\nHello, world\n" in result
    assert "世界。" not in result
    assert "吧！" not in result
