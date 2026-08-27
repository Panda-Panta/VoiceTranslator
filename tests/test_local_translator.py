from app.core.translator import LocalTranslator


def test_delimiter_parser_preserves_alignment_without_network() -> None:
    translator = object.__new__(LocalTranslator)
    translator.batch_size = 2
    translator._local_complete = lambda _prompt: "你好<|VT_SEGMENT|>世界"  # type: ignore[method-assign]
    from app.models import TranscriptionSegment

    result = translator._translate_local_batch(
        [TranscriptionSegment(1, 0, 1, "Hello"), TranscriptionSegment(2, 1, 2, "World")],
        "Hello World",
        "中文",
    )
    assert result == ["你好", "世界"]


def test_invalid_batch_preamble_falls_back_to_strict_single_segments() -> None:
    translator = object.__new__(LocalTranslator)
    translator.batch_size = 2
    responses = iter(
        [
            "整批翻译摘要第一行\n第二行\n第三行<|VT_SEGMENT|>世界",
            "你好",
            "世界",
        ]
    )
    translator._local_complete = lambda _prompt: next(responses)  # type: ignore[method-assign]
    from app.models import TranscriptionSegment

    result = translator._translate_local_batch(
        [TranscriptionSegment(1, 0, 1, "Hello"), TranscriptionSegment(2, 1, 2, "World")],
        "Hello World",
        "中文",
    )
    assert result == ["你好", "世界"]


def test_single_translation_cleans_wrappers_and_rejects_prompt_leakage() -> None:
    translator = object.__new__(LocalTranslator)
    translator._local_complete = lambda _prompt: "译文：<待翻译>你好</待翻译>"  # type: ignore[method-assign]
    assert translator._translate_one("こんにちは", "unused context", "中文") == "你好"
    assert not translator._valid_translation("こんにちは", "只翻译待翻译标签")
