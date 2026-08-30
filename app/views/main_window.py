from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from qfluentwidgets import FluentIcon, FluentWindow, NavigationItemPosition, Theme, setTheme, setThemeColor

from app.config import AppConfig, ConfigStore
from app.i18n import I18n
from app.ui_background import background_rect, normalize_background_scale_mode
from app.views.home_interface import HomeInterface
from app.views.settings_interfaces import (
    ASRSettingsInterface,
    AboutInterface,
    GeneralSettingsInterface,
    TranslationSettingsInterface,
)


def _resource_path(name: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / name


class MainWindow(FluentWindow):
    def __init__(self, config: AppConfig, store: ConfigStore) -> None:
        super().__init__()
        self.config = config
        self.store = store
        self.i18n = I18n(config.language)
        self._background_pixmap = QPixmap()
        self._apply_theme()
        self.home = HomeInterface(config, self)
        self.general = GeneralSettingsInterface(config, store)
        self.general.appearanceChanged.connect(self._apply_appearance)
        self.asr = ASRSettingsInterface(config, store)
        self.translation = TranslationSettingsInterface(config, store)
        self.about = AboutInterface()
        self.addSubInterface(self.home, FluentIcon.HOME, self.i18n("home"))
        self.addSubInterface(
            self.general, FluentIcon.SETTING, self.i18n("general_settings"), NavigationItemPosition.BOTTOM
        )
        self.addSubInterface(
            self.asr, FluentIcon.MICROPHONE, self.i18n("asr_settings"), NavigationItemPosition.BOTTOM
        )
        self.addSubInterface(
            self.translation, FluentIcon.LANGUAGE, self.i18n("translation_settings"), NavigationItemPosition.BOTTOM
        )
        self.addSubInterface(self.about, FluentIcon.INFO, self.i18n("about"), NavigationItemPosition.BOTTOM)
        self.setWindowTitle("VoiceTranslator")
        self.setWindowIcon(QIcon(str(_resource_path("icon.png"))))
        self.resize(1120, 760)
        self.setMinimumSize(900, 640)
        self._reload_background()

    def _apply_theme(self) -> None:
        theme = {"light": Theme.LIGHT, "dark": Theme.DARK}.get(self.config.theme, Theme.AUTO)
        setTheme(theme)
        setThemeColor(QColor(self.config.theme_color))

    def _apply_appearance(self) -> None:
        self._apply_theme()
        self._reload_background()

    def _reload_background(self) -> None:
        self._background_pixmap = QPixmap()
        if self.config.background_enabled:
            path = Path(self.config.background_image_path).expanduser()
            if path.is_file():
                self._background_pixmap.load(str(path))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        pixmap = self._background_pixmap
        if pixmap.isNull() or not self.config.background_enabled:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(max(0, min(100, self.config.background_opacity)) / 100)
        mode = normalize_background_scale_mode(self.config.background_scale_mode)
        if mode == "tile":
            painter.drawTiledPixmap(self.rect(), pixmap)
            return
        target = background_rect(pixmap.width(), pixmap.height(), self.width(), self.height(), mode)
        painter.drawPixmap(QRect(target.x, target.y, target.width, target.height), pixmap)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.home._worker:
            self.home._worker.cancel()
        self.store.save(self.config)
        super().closeEvent(event)
