from app.core.subtitle_segmenter import SubtitleSegmenter
from app.models import TranscriptionSegment


def test_splits_long_cues_near_punctuation_and_removes_small_overlap() -> None:
    segments = [
        TranscriptionSegment(1, 0.0, 8.0, "第一句话很长，需要在这里切开，后面还有另一部分。"),
        TranscriptionSegment(2, 7.8, 10.0, "下一句话。"),
    ]
    result = SubtitleSegmenter(max_chars=16, max_duration=6.0).resegment(segments)
    assert len(result) >= 3
    assert all(result[index].start_time >= result[index - 1].end_time for index in range(1, len(result)))
    assert "".join(item.text for item in result[:2]) == segments[0].text


def test_merges_rapid_short_shouts() -> None:
    segments = [
        TranscriptionSegment(1, 1.0, 1.6, "停下！"),
        TranscriptionSegment(2, 1.7, 2.3, "住手！"),
        TranscriptionSegment(3, 2.4, 3.0, "快跑！"),
    ]
    result = SubtitleSegmenter(max_chars=20, merge_gap_ms=250).resegment(segments)
    assert len(result) == 1
    assert result[0].text == "停下！住手！快跑！"
