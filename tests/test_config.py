import json
import sys
from pathlib import Path

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
    config = AppConfig(crispasr_path="crispasr", asr_model_path="old-qwen.gguf")

    assert resolve_whisper_runtime(config, [tmp_path])
    assert config.crispasr_path == str(executable)
    assert config.asr_model_path == str(model)
    assert config.asr_vad_model_path == str(vad)


def test_valid_custom_whisper_paths_are_not_overwritten(tmp_path: Path) -> None:
    executable = tmp_path / "custom" / "crispasr.exe"
    model = tmp_path / "custom" / "whisper.bin"
    executable.parent.mkdir()
    executable.touch()
    model.touch()
    config = AppConfig(
        crispasr_path=str(executable),
        asr_model_path=str(model),
        asr_vad_enabled=False,
    )

    assert not resolve_whisper_runtime(config, [tmp_path])
    assert config.crispasr_path == str(executable)
    assert config.asr_model_path == str(model)


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
