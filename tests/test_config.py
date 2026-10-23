import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from app.config import AppConfig, ConfigStore, resolve_separation_runtime, resolve_whisper_runtime


def _install_runtime(root: Path) -> tuple[Path, Path, Path]:
    executable = root / "runtime" / "whisper" / "bin" / "crispasr.exe"
    model = root / "runtime" / "whisper" / "models" / "ggml-large-v2-q8_0.bin"
    vad = root / "runtime" / "whisper" / "models" / "ggml-silero-v6.2.0.bin"
    for path in (executable, model, vad):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    manifest = {
        "model": "large-v2-q8_0",
        "crispasr_path": str(executable),
        "whisper_model_path": str(model),
        "vad_model_path": str(vad),
    }
    (root / "runtime" / "whisper" / "runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
    return executable, model, vad


def test_runtime_manifest_repairs_stale_paths(tmp_path: Path) -> None:
    executable, model, vad = _install_runtime(tmp_path)
    config = AppConfig(crispasr_path="crispasr", asr_whisper_model_path="old-whisper.bin")

    assert resolve_whisper_runtime(config, [tmp_path])
    assert config.crispasr_path == str(executable)
    assert config.asr_whisper_model_path == str(model)
    assert config.asr_vad_model_path == str(vad)


def test_valid_custom_whisper_paths_are_not_overwritten(tmp_path: Path) -> None:
    executable = tmp_path / "custom" / "crispasr.exe"
    model = tmp_path / "custom" / "whisper.bin"
    executable.parent.mkdir()
    executable.touch()
    model.touch()
    config = AppConfig(
        crispasr_path=str(executable),
        asr_whisper_model_path=str(model),
        asr_vad_enabled=False,
    )

    assert not resolve_whisper_runtime(config, [tmp_path])
    assert config.crispasr_path == str(executable)
    assert config.asr_whisper_model_path == str(model)


def test_portable_layout_fills_whisper_path_without_runtime_manifest(tmp_path: Path) -> None:
    executable = tmp_path / "runtime" / "whisper" / "bin" / "crispasr.exe"
    model = tmp_path / "models" / "whisper" / "ggml-large-v2-q8_0.bin"
    vad = tmp_path / "models" / "whisper" / "ggml-silero-v6.2.0.bin"
    for path in (executable, model, vad):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    config = AppConfig()

    assert resolve_whisper_runtime(config, [tmp_path])
    assert config.crispasr_path == str(executable)
    assert config.asr_whisper_model_path == str(model)
    assert config.asr_vad_model_path == str(vad)


@pytest.mark.parametrize("include_backend", [False, True])
def test_legacy_whisper_settings_migrate(tmp_path: Path, monkeypatch, include_backend: bool) -> None:
    monkeypatch.setattr("app.config._application_roots", lambda: [tmp_path])
    model = tmp_path / "whisper.bin"
    model.touch()
    raw = {
        "asr_model_path": str(model),
        "asr_extra_args": "--temperature 0",
        "asr_vad_enabled": False,
    }
    if include_backend:
        raw["asr_backend"] = "whisper"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = ConfigStore(path).load()

    assert config.asr_whisper_model_path == str(model)
    assert config.asr_whisper_extra_args == "--temperature 0"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "asr_backend" not in saved
    assert "asr_model_path" not in saved
    assert "asr_extra_args" not in saved


@pytest.mark.parametrize("backend", ["whisper", "qwen3-1.7b"])
def test_retired_asr_config_preserves_whisper_and_other_settings(tmp_path: Path, monkeypatch, backend: str) -> None:
    monkeypatch.setattr("app.config._application_roots", lambda: [tmp_path])
    whisper = tmp_path / "whisper.bin"
    whisper.touch()
    qwen = tmp_path / "qwen3-asr.gguf"
    qwen.write_bytes(b"existing model data")
    path = tmp_path / "config.json"
    raw = {
        "asr_backend": backend,
        "asr_whisper_model_path": str(whisper),
        "asr_whisper_extra_args": "--temperature 0",
        "asr_model_path": str(qwen),
        "asr_aligner_model_path": "old-aligner.gguf",
        "asr_extra_args": "--max-new-tokens 96",
        "asr_qwen3_model_path": str(qwen),
        "asr_qwen3_aligner_model_path": "aligner.gguf",
        "asr_qwen3_lid_model_path": "missing-lid.bin",
        "asr_qwen3_extra_args": "--frequency-penalty 0.8",
        "asr_vad_enabled": False,
        "asr_language": "ja",
        "translation_model_path": "Qwen-translation.gguf",
        "api_key": "test-only-key",
        "theme": "dark",
        "ui_font_scale": 150,
    }
    path.write_text(json.dumps(raw), encoding="utf-8")

    store = ConfigStore(path)
    config = store.load()

    assert config.asr_whisper_model_path == str(whisper)
    assert config.asr_whisper_extra_args == "--temperature 0"
    assert config.asr_language == "ja"
    assert config.translation_model_path == "Qwen-translation.gguf"
    assert config.api_key == "test-only-key"
    assert config.theme == "dark"
    assert config.ui_font_scale == 150
    assert qwen.read_bytes() == b"existing model data"
    saved = json.loads(path.read_text(encoding="utf-8"))
    retired = {
        "asr_backend", "asr_model_path", "asr_aligner_model_path", "asr_extra_args",
        "asr_qwen3_model_path", "asr_qwen3_aligner_model_path", "asr_qwen3_lid_model_path", "asr_qwen3_extra_args",
    }
    assert retired.isdisjoint(saved)
    assert retired.isdisjoint(asdict(config))
    assert asdict(ConfigStore(path).load()) == asdict(config)


@pytest.mark.parametrize("installed_whisper", [False, True])
def test_old_qwen_shared_settings_never_become_whisper_settings(tmp_path: Path, monkeypatch, installed_whisper: bool) -> None:
    monkeypatch.setattr("app.config._application_roots", lambda: [tmp_path])
    expected_model = str(_install_runtime(tmp_path)[1]) if installed_whisper else ""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "asr_backend": "qwen3-1.7b",
        "asr_model_path": "qwen-old.gguf",
        "asr_aligner_model_path": "aligner-old.gguf",
        "asr_extra_args": "--max-new-tokens 96",
        "asr_vad_enabled": False,
    }), encoding="utf-8")

    config = ConfigStore(path).load()

    assert config.asr_whisper_model_path == expected_model
    assert config.asr_whisper_extra_args == ""
    assert json.loads(path.read_text(encoding="utf-8")) == asdict(config)


def test_separation_manifest_fills_official_onnx_model(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime" / "separation"
    mdx = runtime / "models" / "model.onnx"
    mdx.parent.mkdir(parents=True, exist_ok=True)
    mdx.touch()
    (runtime / "runtime.json").write_text(json.dumps({"mdx_model_path": str(mdx)}), encoding="utf-8")
    config = AppConfig()
    assert resolve_separation_runtime(config, [tmp_path])
    assert config.vocal_separation_model_path == str(mdx)


def test_default_font_scale_is_larger_than_system_default() -> None:
    assert AppConfig().ui_font_scale == 125


def test_frozen_portable_build_uses_local_config(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / "VoiceTranslator.exe"
    executable.touch()
    (tmp_path / "portable.flag").touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert ConfigStore().path == tmp_path / "config.json"


def test_frozen_build_without_portable_flag_uses_appdata(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / "VoiceTranslator.exe"
    executable.touch()
    appdata = tmp_path / "AppData"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setenv("APPDATA", str(appdata))

    assert ConfigStore().path == appdata / "VoiceTranslator" / "config.json"
