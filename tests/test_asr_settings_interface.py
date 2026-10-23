from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from qfluentwidgets import PrimaryPushButton

from app.config import AppConfig, ConfigStore
from app.views.settings_interfaces import ASRSettingsInterface


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("vad_enabled", [True, False])
def test_whisper_settings_save_and_reopen_preserves_other_settings(tmp_path, monkeypatch, vad_enabled) -> None:
    _application()
    monkeypatch.setattr("app.config._application_roots", lambda: [tmp_path])
    monkeypatch.setattr("app.views.settings_interfaces.InfoBar.success", lambda *args, **kwargs: None)
    config = AppConfig(
        asr_whisper_model_path="whisper-old.bin",
        asr_whisper_extra_args="--temperature 0",
        asr_language="ja",
        translation_model_path="qwen-translation.gguf",
    )
    config_path = tmp_path / "config.json"
    page = ASRSettingsInterface(config, ConfigStore(config_path))
    model_path = str(tmp_path / "ggml-large-v3-turbo-q5_0.bin")
    vad_path = str(tmp_path / "ggml-silero-v6.2.0.bin")

    assert page.whisper_model.text() == "whisper-old.bin"
    assert page.whisper_extra.text() == "--temperature 0"
    page.whisper_model.edit.setText(f"  {model_path}  ")
    page.whisper_extra.setText("  --temperature 0.1  ")
    page.gpu.setValue(0)
    page.threads.setValue(3)
    page.vad.setChecked(vad_enabled)
    page.vad_model.edit.setText(vad_path)
    page.vad_silence.setValue(700)
    page.vad_speech_pad.setValue(200)
    page.subtitle_max_chars.setValue(36)
    page.subtitle_max_duration.setValue(7.5)
    assert page.whisper_model_detected.text() == "large-v3-turbo-q5_0"

    page.findChild(PrimaryPushButton).click()
    page.close()
    loaded = ConfigStore(config_path).load()
    assert loaded.asr_whisper_model_path == model_path
    assert loaded.asr_whisper_extra_args == "--temperature 0.1"
    assert loaded.asr_language == "ja"
    assert loaded.translation_model_path == "qwen-translation.gguf"

    reopened = ASRSettingsInterface(loaded, ConfigStore(config_path))
    assert reopened.whisper_model.text() == model_path
    assert reopened.whisper_extra.text() == "--temperature 0.1"
    assert reopened.whisper_model_detected.text() == "large-v3-turbo-q5_0"
    assert reopened.gpu.value() == 0
    assert reopened.threads.value() == 3
    assert reopened.vad.isChecked() is vad_enabled
    assert reopened.vad_model.text() == vad_path
    assert reopened.vad_silence.value() == 700
    assert reopened.vad_speech_pad.value() == 200
    assert reopened.subtitle_max_chars.value() == 36
    assert reopened.subtitle_max_duration.value() == 7.5
    reopened.close()
