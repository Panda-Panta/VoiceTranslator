from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget


MIN_FONT_SCALE = 80
MAX_FONT_SCALE = 200
DEFAULT_FONT_SCALE = 125
_BASE_FONT_SIZE_PROPERTY = "voiceTranslatorBaseFontPointSize"
_BASE_WIDGET_FONT_PROPERTY = "voiceTranslatorBaseWidgetFont"
_FONT_SCALE_PROPERTY = "voiceTranslatorFontScale"


def _scale_widget_font(widget: QWidget, scale: int) -> None:
    """Update both Fluent pixel fonts and Qt fonts across stylesheet boundaries."""
    base_font = widget.property(_BASE_WIDGET_FONT_PROPERTY)
    font = widget.font()
    if (not isinstance(base_font, QFont) and widget.testAttribute(Qt.WA_SetFont)
            and font.pixelSize() > 0):
        base_font = QFont(widget.font())
        widget.setProperty(_BASE_WIDGET_FONT_PROPERTY, base_font)
    if isinstance(base_font, QFont):
        font = QFont(base_font)
        font.setPixelSize(max(1, round(base_font.pixelSize() * scale / 100)))
    elif font.pixelSize() <= 0:
        # QSS-styled parent containers can retain an old inherited application
        # font. Set the size explicitly while preserving family and weight.
        font.setPointSizeF(QApplication.instance().font().pointSizeF())
    else:
        return
    if widget.font() != font:
        widget.setFont(font)
        widget.updateGeometry()


class _FontScaleFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Polish and isinstance(watched, QWidget):
            app = QApplication.instance()
            _scale_widget_font(watched, app.property(_FONT_SCALE_PROPERTY) or 100)
        return False


def normalize_font_scale(value: int | float) -> int:
    return max(MIN_FONT_SCALE, min(MAX_FONT_SCALE, round(float(value))))


def apply_font_scale(scale_percent: int | float, application: QApplication | None = None) -> None:
    """Scale inherited Qt fonts and explicit Fluent fonts without accumulating."""
    app = application or QApplication.instance()
    if app is None:
        return
    base_size = app.property(_BASE_FONT_SIZE_PROPERTY)
    if not isinstance(base_size, (int, float)) or base_size <= 0:
        base_size = app.font().pointSizeF()
        if base_size <= 0:
            base_size = 9.0
        app.setProperty(_BASE_FONT_SIZE_PROPERTY, base_size)
    scale = normalize_font_scale(scale_percent)
    app.setProperty(_FONT_SCALE_PROPERTY, scale)
    if not hasattr(app, "_voice_translator_font_filter"):
        app._voice_translator_font_filter = _FontScaleFilter(app)
        app.installEventFilter(app._voice_translator_font_filter)
    # Capture all original explicit fonts before changing a parent font, so a
    # child's inherited size cannot become the baseline of a second scaling.
    widgets = app.allWidgets()
    for widget in widgets:
        if (widget.property(_BASE_WIDGET_FONT_PROPERTY) is None
                and widget.testAttribute(Qt.WA_SetFont) and widget.font().pixelSize() > 0):
            widget.setProperty(_BASE_WIDGET_FONT_PROPERTY, QFont(widget.font()))
    font = app.font()
    font.setPointSizeF(float(base_size) * scale / 100.0)
    app.setFont(font)
    for widget in widgets:
        _scale_widget_font(widget, scale)
