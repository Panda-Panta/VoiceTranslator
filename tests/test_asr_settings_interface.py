from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.config import AppConfig, ConfigStore
from app.views.settings_interfaces import ASRSettingsInterface


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_switching_asr_backend_preserves_each_backends_model_path(tmp_path) -> None:
    _application()
    config = AppConfig(
        asr_backend="qwen3-1.7b",
        asr_whisper_model_path="whisper-old.bin",
        asr_qwen3_model_path="qwen-main.gguf",
        asr_whisper_extra_args="--whisper-option",
        asr_qwen3_extra_args="--qwen-option",
    )
    page = ASRSettingsInterface(config, ConfigStore(tmp_path / "config.json"))

    page.backend.setCurrentIndex(page.backend.findData("whisper"))
    page.whisper_model.edit.setText("whisper-large-v2.bin")
    page.whisper_extra.setText("--whisper-new")
    page.backend.setCurrentIndex(page.backend.findData("qwen3-1.7b"))

    assert page.qwen_model.text() == "qwen-main.gguf"
    assert page.qwen_extra.text() == "--qwen-option"
    assert page.model_stack.currentIndex() == 1
    assert page.extra_stack.currentIndex() == 1

    page._save()
    assert config.asr_whisper_model_path == "whisper-large-v2.bin"
    assert config.asr_qwen3_model_path == "qwen-main.gguf"
    assert config.asr_whisper_extra_args == "--whisper-new"
    assert config.asr_qwen3_extra_args == "--qwen-option"
