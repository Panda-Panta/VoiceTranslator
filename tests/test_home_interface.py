from app.models import ProcessMode
from app.views.home_interface import HomeInterface


def test_translate_segment_creates_translation_task() -> None:
    assert HomeInterface._process_mode_from_key("translate") is ProcessMode.TRANSCRIBE_AND_TRANSLATE


def test_transcribe_segment_creates_transcribe_only_task() -> None:
    assert HomeInterface._process_mode_from_key("transcribe") is ProcessMode.TRANSCRIBE_ONLY
    assert HomeInterface._process_mode_from_key(None) is ProcessMode.TRANSCRIBE_ONLY
