import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.models import ProcessMode
from app.views.home_interface import HomeInterface


def test_translate_segment_creates_translation_task() -> None:
    assert HomeInterface._process_mode_from_key("translate") is ProcessMode.TRANSCRIBE_AND_TRANSLATE


def test_transcribe_segment_creates_transcribe_only_task() -> None:
    assert HomeInterface._process_mode_from_key("transcribe") is ProcessMode.TRANSCRIBE_ONLY
    assert HomeInterface._process_mode_from_key(None) is ProcessMode.TRANSCRIBE_ONLY


@pytest.mark.parametrize("source_label,source_code", [("自动检测", "auto"), ("日本語", "ja")])
def test_source_and_target_languages_remain_independent_across_modes(source_label, source_code) -> None:
    application = QApplication.instance() or QApplication([])
    config = AppConfig(asr_language="en")
    page = HomeInterface(config)
    page.target_language.setCurrentText("Français")
    page.source_language.setCurrentText(source_label)
    assert config.asr_language == source_code
    assert page.target_language.currentText() == "Français"

    page._sync_mode("transcribe")
    assert page.source_language.isEnabled()
    assert not page.target_language.isEnabled()
    assert page.source_language.currentText() == source_label
    page._sync_mode("translate")
    page.target_language.setCurrentText("简体中文")
    assert page.target_language.isEnabled()
    assert page.source_language.currentText() == source_label
    assert config.asr_language == source_code
    page.close()
