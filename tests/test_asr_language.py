import os
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from app.config import AppConfig, ConfigStore
from app.views.home_interface import HomeInterface


def test_home_source_language_is_saved_and_reaches_task(tmp_path):
    application = QApplication.instance() or QApplication([])
    config = AppConfig(asr_language='ja')
    store = ConfigStore(tmp_path / 'config.json')
    page = HomeInterface(config, store=store)
    assert page.source_language.currentText() == '日本語'
    page.source_language.setCurrentText('English')
    assert config.asr_language == 'en'
    assert store.load().asr_language == 'en'
    audio = tmp_path / 'test.wav'
    audio.touch()
    page.add_files([str(audio)])
    with patch.object(QThread, 'start'):
        page._start()
    assert page._worker.task.source_language == 'English'
    assert page._worker.task.target_language == page.target_language.currentText()
    page._worker = None
    page.close()
