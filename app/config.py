from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


def _default_config_path() -> Path:
    if getattr(sys, "frozen", False):
        executable_root = Path(sys.executable).resolve().parent
        if (executable_root / "portable.flag").is_file():
            return executable_root / "config.json"
    root = Path(os.getenv("APPDATA", Path.home())) / "VoiceTranslator"
    return root / "config.json"


def _application_roots() -> list[Path]:
    candidates = [Path(__file__).resolve().parents[1], Path.cwd()]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).resolve().parent)
    roots: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return roots


@dataclass(slots=True)
class AppConfig:
    theme: str = "system"
    theme_color: str = "#009faa"
    ui_font_scale: int = 125
    background_enabled: bool = False
    background_image_path: str = ""
    background_scale_mode: str = "cover"
    background_opacity: int = 30
    language: str = "zh_CN"
    ffmpeg_path: str = "ffmpeg"
    output_directory: str = ""
    output_directory_mode: str = "source"
    notify_when_done: bool = True
    open_output_directory: bool = False

    llama_server_path: str = "llama-server"
    crispasr_path: str = "crispasr"
    asr_backend: str = "whisper"
    asr_whisper_model_path: str = ""
    asr_qwen3_model_path: str = ""
    asr_qwen3_aligner_model_path: str = ""
    asr_qwen3_lid_model_path: str = ""
    asr_gpu_layers: int = 999
    asr_threads: int = max(1, min(32, os.cpu_count() or 4))
    asr_timestamps: bool = True
    asr_language: str = "auto"
    asr_vad_enabled: bool = True
    asr_vad_model_path: str = ""
    asr_vad_min_silence_ms: int = 500
    asr_vad_speech_pad_ms: int = 150
    asr_split_on_punctuation: bool = False
    subtitle_resegment_enabled: bool = True
    subtitle_max_chars: int = 28
    subtitle_max_duration: float = 6.0
    subtitle_merge_gap_ms: int = 250
    asr_device: int = 0
    asr_whisper_extra_args: str = ""
    asr_qwen3_extra_args: str = ""
    vocal_separation_enabled: bool = False
    vocal_separation_model_path: str = ""

    translation_engine: str = "local"
    translation_model_path: str = ""
    translation_gpu_layers: int = 999
    translation_context_size: int = 8192
    translation_port: int = 8080
    api_base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    api_model: str = ""
    temperature: float = 0.2
    translation_prompt: str = ""
    batch_size: int = 10
    server_start_timeout: float = 120.0
    auto_unload_models: bool = True

    def selected_asr_model_path(self) -> str:
        if self.asr_backend == "qwen3-1.7b":
            return self.asr_qwen3_model_path
        return self.asr_whisper_model_path

    def selected_asr_aligner_model_path(self) -> str:
        return self.asr_qwen3_aligner_model_path if self.asr_backend == "qwen3-1.7b" else ""

    def selected_asr_extra_args(self) -> str:
        if self.asr_backend == "qwen3-1.7b":
            return self.asr_qwen3_extra_args
        return self.asr_whisper_extra_args


def _migrate_legacy_asr_config(raw: dict[str, Any]) -> bool:
    """Move the former shared ASR fields into the selected backend once."""
    changed = False
    backend = str(raw.get("asr_backend", "whisper"))
    model = str(raw.get("asr_model_path", "")).strip()
    if model:
        target = "asr_qwen3_model_path" if backend == "qwen3-1.7b" else "asr_whisper_model_path"
        if target not in raw:
            raw[target] = model
            changed = True
    aligner = str(raw.get("asr_aligner_model_path", "")).strip()
    if aligner and "asr_qwen3_aligner_model_path" not in raw:
        raw["asr_qwen3_aligner_model_path"] = aligner
        changed = True
    extra_args = str(raw.get("asr_extra_args", "")).strip()
    if extra_args:
        target = "asr_qwen3_extra_args" if backend == "qwen3-1.7b" else "asr_whisper_extra_args"
        if target not in raw:
            raw[target] = extra_args
            changed = True
    for legacy_name in ("asr_model_path", "asr_aligner_model_path", "asr_extra_args"):
        if legacy_name in raw:
            raw.pop(legacy_name)
            changed = True
    return changed


def resolve_whisper_runtime(config: AppConfig, roots: list[Path] | None = None) -> bool:
    """Repair shared runtime paths and the dedicated Whisper model path."""
    executable_ok = Path(config.crispasr_path).is_file()
    model_ok = Path(config.asr_whisper_model_path).is_file()
    vad_ok = not config.asr_vad_enabled or Path(config.asr_vad_model_path).is_file()
    if executable_ok and model_ok and vad_ok:
        return False

    for root in roots or _application_roots():
        manifest_path = root / "runtime" / "whisper" / "runtime.json"
        manifest: dict[str, Any] = {}
        try:
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, TypeError):
            manifest = {}
        model_root = root / "models" / "whisper"
        legacy_model_root = root / "runtime" / "whisper" / "models"
        executable = _first_existing_file(
            manifest.get("crispasr_path"),
            root / "runtime" / "whisper" / "bin" / "crispasr.exe",
            root / "crispasr" / "crispasr.exe",
        )
        model = _first_existing_file(
            manifest.get("whisper_model_path"),
            model_root / "ggml-large-v2-q8_0.bin",
            legacy_model_root / "ggml-large-v2-q8_0.bin",
            *sorted(model_root.glob("ggml-large-v*.bin")),
            *sorted(legacy_model_root.glob("ggml-large-v*.bin")),
        )
        vad = _first_existing_file(
            manifest.get("vad_model_path"),
            model_root / "ggml-silero-v6.2.0.bin",
            legacy_model_root / "ggml-silero-v6.2.0.bin",
        )
        changed = False
        if not executable_ok and executable is not None:
            config.crispasr_path = str(executable)
            changed = True
        if not model_ok and model is not None:
            config.asr_whisper_model_path = str(model)
            changed = True
        if config.asr_vad_enabled and not vad_ok and vad is not None:
            config.asr_vad_model_path = str(vad)
            changed = True
        if changed:
            config.asr_timestamps = True
            return True
    return False


def resolve_lid_runtime(config: AppConfig, roots: list[Path] | None = None) -> bool:
    """Discover bundled tiny only for an unset path; never hide a broken custom path."""
    if config.asr_qwen3_lid_model_path:
        return False
    for root in roots or _application_roots():
        candidate = _first_existing_file(
            root / "models" / "lid" / "ggml-tiny.bin",
            root / "runtime" / "lid" / "ggml-tiny.bin",
        )
        if candidate is not None:
            config.asr_qwen3_lid_model_path = str(candidate)
            return True
    return False


def _first_existing_file(*values: object) -> Path | None:
    for value in values:
        if value is None or str(value).strip() == "":
            continue
        path = Path(str(value)).expanduser()
        if path.is_file():
            return path
    return None


def resolve_separation_runtime(config: AppConfig, roots: list[Path] | None = None) -> bool:
    """Fill missing separator paths from the optional runtime manifest."""
    changed = False
    for root in roots or _application_roots():
        manifest_path = root / "runtime" / "separation" / "runtime.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, TypeError):
            continue
        mappings = {
            "vocal_separation_model_path": "mdx_model_path",
        }
        for config_name, manifest_name in mappings.items():
            current_value = str(getattr(config, config_name, "")).strip()
            current = Path(current_value).expanduser() if current_value else None
            candidate = Path(str(manifest.get(manifest_name, ""))).expanduser()
            if (current is None or not current.exists()) and candidate.exists():
                setattr(config, config_name, str(candidate))
                changed = True
        break
    return changed


class ConfigStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else _default_config_path()
        self.value = AppConfig()

    def load(self) -> AppConfig:
        if not self.path.exists():
            resolve_lid_runtime(self.value)
            resolve_whisper_runtime(self.value)
            resolve_separation_runtime(self.value)
            return self.value
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
            migrated = _migrate_legacy_asr_config(raw)
            allowed = {item.name for item in fields(AppConfig)}
            self.value = AppConfig(**{key: val for key, val in raw.items() if key in allowed})
            changed = resolve_whisper_runtime(self.value)
            changed = resolve_lid_runtime(self.value) or changed
            changed = resolve_separation_runtime(self.value) or changed
            if changed or migrated:
                self.save()
        except (OSError, ValueError, TypeError):
            self.value = AppConfig()
            resolve_lid_runtime(self.value)
            resolve_whisper_runtime(self.value)
            resolve_separation_runtime(self.value)
        return self.value

    def save(self, config: AppConfig | None = None) -> None:
        if config is not None:
            self.value = config
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self.value), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def update(self, **values: Any) -> AppConfig:
        allowed = {item.name for item in fields(AppConfig)}
        for key, value in values.items():
            if key in allowed:
                setattr(self.value, key, value)
        self.save()
        return self.value
