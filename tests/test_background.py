from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.config import AppConfig, ConfigStore
from app.ui_background import BackgroundRect, background_rect, normalize_background_scale_mode
from app.views.main_window import MainWindow
from app.views.settings_interfaces import GeneralSettingsInterface


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_background_scaling_geometry() -> None:
    assert background_rect(400, 200, 200, 200, "cover") == BackgroundRect(-100, 0, 400, 200)
    assert background_rect(400, 200, 200, 200, "contain") == BackgroundRect(0, 50, 200, 100)
    assert background_rect(400, 200, 200, 200, "stretch") == BackgroundRect(0, 0, 200, 200)
    assert normalize_background_scale_mode("unknown") == "cover"


def test_background_settings_round_trip_and_load_image(tmp_path) -> None:
    _application()
    image_path = tmp_path / "background.png"
    image = QImage(16, 8, QImage.Format_RGB32)
    image.fill(QColor("#336699"))
    assert image.save(str(image_path))
    config_path = tmp_path / "config.json"
    config = AppConfig(
        background_enabled=True,
        background_image_path=str(image_path),
        background_scale_mode="contain",
        background_opacity=45,
    )
    store = ConfigStore(config_path)
    store.save(config)

    loaded = ConfigStore(config_path).load()
    page = GeneralSettingsInterface(loaded, ConfigStore(config_path))
    window = MainWindow(loaded, ConfigStore(config_path))

    assert page.background_enabled.isChecked()
    assert page.background_scale.currentData() == "contain"
    assert page.background_opacity.value() == 45
    assert not page.viewport().autoFillBackground()
    assert not page.widget().autoFillBackground()
    assert not window._background_pixmap.isNull()

    loaded.background_enabled = False
    window.general.appearanceChanged.emit()
    assert window._background_pixmap.isNull()
