from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.config import ConfigStore
from app.ui_scale import apply_font_scale
from app.views import MainWindow


def main() -> int:
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)
    application = QApplication(sys.argv)
    application.setApplicationName("VoiceTranslator")
    store = ConfigStore()
    config = store.load()
    apply_font_scale(config.ui_font_scale, application)
    window = MainWindow(config, store)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
