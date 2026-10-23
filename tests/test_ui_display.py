from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QFont, QFontDatabase, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from qfluentwidgets import PushButton, SubtitleLabel, Theme, setTheme

from app.config import AppConfig, ConfigStore
from app.ui_scale import apply_font_scale
from app.views.main_window import MainWindow


@pytest.fixture
def display_application():
    application = QApplication.instance() or QApplication([])
    previous_font = application.font()
    previous_base = application.property("voiceTranslatorBaseFontPointSize")
    previous_scale = application.property("voiceTranslatorFontScale")
    for name in ("msyh.ttc", "segoeui.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    application.setFont(QFont("Microsoft YaHei", 9))
    application.setProperty("voiceTranslatorBaseFontPointSize", 9.0)
    yield application
    apply_font_scale(previous_scale or 100, application)
    application.setFont(previous_font)
    application.setProperty("voiceTranslatorBaseFontPointSize", previous_base)


def test_live_font_changes_scale_fluent_controls_without_accumulating(display_application, tmp_path):
    application = display_application
    config = AppConfig(theme="light", ui_font_scale=125)
    window = MainWindow(config, ConfigStore(tmp_path / "config.json"))
    window.show()
    try:
        title = window.home.findChild(SubtitleLabel)
        for scale in (200, 80, 125, 200, 125):
            apply_font_scale(scale, application)
            application.processEvents()
            assert application.font().pointSizeF() == pytest.approx(9 * scale / 100)
            assert window.home.start_button.font().pixelSize() == round(14 * scale / 100)
            assert window.home.source_language.font().pointSizeF() == pytest.approx(9 * scale / 100)
            assert window.home.log_output.font().pixelSize() == round(14 * scale / 100)
            assert title.font().pixelSize() == round(20 * scale / 100)
            for widget in (window.home.table, window.asr.gpu, window.asr.whisper_model.edit):
                assert widget.font().pointSizeF() == pytest.approx(9 * scale / 100)
            assert window.home.start_button.height() >= window.home.start_button.sizeHint().height()

        # Newly created Fluent controls must also pick up the active scale.
        button = PushButton("Later control", window.home)
        button.ensurePolished()
        assert button.font().pixelSize() == round(14 * 1.25)
        button.deleteLater()
    finally:
        window.close()
        window.deleteLater()
        application.sendPostedEvents(None, QEvent.DeferredDelete)


def test_saved_theme_changes_keep_native_controls_and_rendered_page_readable(display_application, tmp_path, monkeypatch):
    application = display_application
    window = MainWindow(AppConfig(theme="light"), ConfigStore(tmp_path / "config.json"))
    # QWidget.grab does not include the Windows DWM Mica backdrop.
    window.setMicaEffectEnabled(False)
    window.resize(900, 640)
    window.show()
    window.switchTo(window.general)
    monkeypatch.setattr("app.views.settings_interfaces.InfoBar.success", lambda *_, **__: None)
    try:
        for theme, scale in ((Theme.DARK, 200), (Theme.LIGHT, 80), (Theme.DARK, 125)):
            window.general.theme.setCurrentIndex(2 if theme == Theme.DARK else 1)
            window.general.font_scale.setValue(scale)
            window.general._save()
            QTest.qWait(350)
            application.processEvents()
            dark = theme == Theme.DARK
            label = next(label for label in window.general.findChildren(QLabel) if label.text() == "主题模式")
            palette = label.palette()
            text = palette.color(QPalette.WindowText).lightness()
            field_base = window.general.server.edit.palette().color(QPalette.Base).lightness()
            table_base = window.home.table.palette().color(QPalette.Base).lightness()
            assert (text > field_base) is dark
            assert (table_base < 128) is dark
            # Test the rendered page backdrop, not only palette properties.
            point = window.general.mapTo(window, QPoint(5, 5))
            pixel = window.grab().toImage().pixelColor(point)
            assert pixel.alpha() == 255
            assert (pixel.lightness() < 128) is dark
            assert window.asr.gpu.font().pointSizeF() == pytest.approx(9 * scale / 100)
            assert window.home.start_button.font().pixelSize() == round(14 * scale / 100)
    finally:
        window.close()
        window.deleteLater()
        application.sendPostedEvents(None, QEvent.DeferredDelete)
        setTheme(Theme.LIGHT)
