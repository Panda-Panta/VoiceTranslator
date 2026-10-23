from __future__ import annotations

from PySide6.QtWidgets import QApplication


MIN_FONT_SCALE = 80
MAX_FONT_SCALE = 200
DEFAULT_FONT_SCALE = 125
_BASE_FONT_SIZE_PROPERTY = "voiceTranslatorBaseFontPointSize"


def normalize_font_scale(value: int | float) -> int:
    return max(MIN_FONT_SCALE, min(MAX_FONT_SCALE, round(float(value))))


def apply_font_scale(scale_percent: int | float, application: QApplication | None = None) -> None:
    """Apply a non-cumulative application-wide font scale."""
    app = application or QApplication.instance()
    if app is None:
        return
    base_size = app.property(_BASE_FONT_SIZE_PROPERTY)
    if not isinstance(base_size, (int, float)) or base_size <= 0:
        base_size = app.font().pointSizeF()
        if base_size <= 0:
            base_size = 9.0
        app.setProperty(_BASE_FONT_SIZE_PROPERTY, base_size)
    font = app.font()
    font.setPointSizeF(float(base_size) * normalize_font_scale(scale_percent) / 100.0)
    app.setFont(font)
