from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QRect
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from qfluentwidgets import PrimaryPushButton

from app.config import AppConfig, ConfigStore
from app.ui_scale import apply_font_scale
from app.views.settings_interfaces import ASRSettingsInterface, TranslationSettingsInterface


@pytest.fixture
def application():
    app = QApplication.instance() or QApplication([])
    previous_font = app.font()
    previous_base = app.property("voiceTranslatorBaseFontPointSize")
    previous_scale = app.property("voiceTranslatorFontScale")
    for font_path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"):
        if Path(font_path).is_file():
            QFontDatabase.addApplicationFont(font_path)
    app.setFont(QFont("Microsoft YaHei", 9))
    app.setProperty("voiceTranslatorBaseFontPointSize", 9.0)
    yield app
    apply_font_scale(previous_scale if previous_scale is not None else 100, app)
    app.setFont(previous_font)
    app.setProperty("voiceTranslatorBaseFontPointSize", previous_base)
    app.setProperty("voiceTranslatorFontScale", previous_scale)


def _process_layout(application: QApplication) -> None:
    for _ in range(6):
        application.processEvents()


def _assert_page_fits_and_save_is_reachable(page, application: QApplication) -> None:
    _process_layout(application)
    assert page.widget().width() <= page.viewport().width()
    assert page.horizontalScrollBar().maximum() == 0
    save = page.findChild(PrimaryPushButton)
    assert save is not None
    page.ensureWidgetVisible(save)
    _process_layout(application)
    save_rect = QRect(save.mapTo(page.viewport(), QPoint()), save.size())
    assert page.viewport().rect().contains(save_rect)


@pytest.mark.parametrize("scale", [80, 125, 200])
@pytest.mark.parametrize("name", [
    "whisper-large-v3-turbo-japanese-english-transcription-q5_0",
    "verylongfilename" * 8,
])
def test_long_whisper_model_name_keeps_settings_within_viewport(application, tmp_path, scale, name) -> None:
    apply_font_scale(scale, application)
    config = AppConfig(asr_whisper_model_path=f"D:/models/ggml-{name}.bin")
    page = ASRSettingsInterface(config, ConfigStore(tmp_path / "config.json"))
    apply_font_scale(scale, application)
    page.resize(851, 591)  # Settings area of the supported 900 x 640 window.
    page.show()
    try:
        _assert_page_fits_and_save_is_reachable(page, application)
        assert page.whisper_model_detected.text() == name
        page.whisper_model_detected.selectAll()
        assert page.whisper_model_detected.selectedText() == name
        assert page.whisper_model_detected.toolTip() == name
    finally:
        page.close()
        page.deleteLater()
        application.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.mark.parametrize("scale", [80, 125, 200])
def test_long_api_model_from_saved_config_and_refresh_keeps_settings_within_viewport(
    application, tmp_path, monkeypatch, scale
) -> None:
    apply_font_scale(scale, application)
    name = "provider/translation-model-long-context-v2.5-instruct-128k-2026-10-23"
    config = AppConfig(api_model=name)
    page = TranslationSettingsInterface(config, ConfigStore(tmp_path / "config.json"))
    apply_font_scale(scale, application)
    page.resize(851, 591)
    page.show()
    monkeypatch.setattr("app.views.settings_interfaces.OnlineTranslator.list_models", lambda *_: [name, name + "-updated"])
    monkeypatch.setattr("app.views.settings_interfaces.InfoBar.success", lambda *_, **__: None)
    try:
        _assert_page_fits_and_save_is_reachable(page, application)
        assert page.api_model.currentText() == name
        page._refresh_models()
        page.api_model.setCurrentIndex(1)
        _assert_page_fits_and_save_is_reachable(page, application)
        assert page.api_model.currentText() == name + "-updated"
    finally:
        page.close()
        page.deleteLater()
        application.sendPostedEvents(None, QEvent.DeferredDelete)
