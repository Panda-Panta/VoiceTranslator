import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRect, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.config import AppConfig
from app.models import ProcessMode
from app.ui_scale import apply_font_scale
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


@pytest.fixture
def home_application() -> QApplication:
    application = QApplication.instance() or QApplication([])
    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf"):
        if Path(path).is_file():
            QFontDatabase.addApplicationFont(path)
    return application


def test_large_home_controls_and_log_remain_accessible(home_application) -> None:
    apply_font_scale(100, home_application)
    page = HomeInterface(AppConfig())
    apply_font_scale(200, home_application)
    page.resize(851, 591)  # Content area of the supported 900 x 640 window.
    page.show()
    home_application.processEvents()
    home_application.processEvents()

    assert page.scroll_area.verticalScrollBar().maximum() > 0
    for widget in (page.source_language, page.target_language, page.export_format, page.content_mode):
        assert widget.height() >= widget.sizeHint().height()
    mode_bottom = page.process_mode.mapTo(page, QPoint(0, page.process_mode.height())).y()
    assert mode_bottom < page.start_button.mapTo(page, QPoint()).y()

    page.scroll_area.verticalScrollBar().setValue(page.scroll_area.verticalScrollBar().maximum())
    home_application.processEvents()
    viewport = page.scroll_area.viewport()
    for widget in (page.start_button, page.cancel_button, page.log_output):
        rectangle = QRect(widget.mapTo(viewport, QPoint()), widget.size())
        assert viewport.rect().contains(rectangle)
    assert page.scroll_area.horizontalScrollBar().maximum() == 0
    page.close()
    apply_font_scale(100, home_application)


def test_file_details_fit_after_font_increase(home_application, tmp_path) -> None:
    subtitle = tmp_path / "sample.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nSample\n", encoding="utf-8")
    page = HomeInterface(AppConfig())
    page.resize(851, 591)
    page.add_files([str(subtitle)])
    page.table.item(0, 2).setText("1023.9 MB")
    page.show()
    home_application.processEvents()

    page.table.setFont(QFont("Microsoft YaHei", 18))
    home_application.processEvents()
    home_application.processEvents()
    metrics = page.table.fontMetrics()
    for column in (1, 2):
        assert page.table.columnWidth(column) >= metrics.horizontalAdvance(page.table.item(0, column).text()) + 6
    assert page.table.rowHeight(0) >= metrics.height() + 4

    page.add_files([str(subtitle)])
    assert page.table.rowCount() == 1
    page.table.selectRow(0)
    page._remove_selected()
    assert page.table.rowCount() == 0
    page.close()


def test_home_language_popup_scales_and_selection_keeps_target(home_application) -> None:
    apply_font_scale(100, home_application)
    config = AppConfig(asr_language="en")
    page = HomeInterface(config)
    page.target_language.setCurrentText("Français")
    apply_font_scale(200, home_application)
    page.resize(851, 591)
    page.show()
    home_application.processEvents()
    page.scroll_area.ensureWidgetVisible(page.source_language)
    page.source_language.showPopup()
    home_application.processEvents()
    view = page.source_language.view()
    assert view.font().pointSizeF() == page.source_language.font().pointSizeF()
    source_index = view.model().index(page.source_language.findText("日本語"), 0)
    view.scrollTo(source_index)
    home_application.processEvents()
    rectangle = view.visualRect(source_index)
    assert rectangle.height() >= view.fontMetrics().height()
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=rectangle.center())
    home_application.processEvents()
    assert page.source_language.currentText() == "日本語"
    assert config.asr_language == "ja"
    assert page.target_language.currentText() == "Français"
    page.close()
    apply_font_scale(100, home_application)


def test_files_dropped_on_scroll_viewport_still_reach_home(home_application, tmp_path) -> None:
    subtitle = tmp_path / "dropped.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nSample\n", encoding="utf-8")
    page = HomeInterface(AppConfig())
    page.resize(851, 591)
    page.show()
    home_application.processEvents()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(subtitle))])
    viewport = page.scroll_area.viewport()
    enter = QDragEnterEvent(QPoint(80, 120), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(viewport, enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(80, 120), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(viewport, drop)
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).data(Qt.UserRole) == str(subtitle)
    page.close()
