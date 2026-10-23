from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.crispasr_engine import CrispASREngine


def test_whisper_command_uses_native_timestamps_vad_and_gpu(tmp_path: Path) -> None:
    engine = CrispASREngine(
        "crispasr.exe",
        "large-v2-q8_0.bin",
        threads=12,
        language="ja",
        vad_enabled=True,
        vad_model_path="silero.bin",
        vad_min_silence_ms=240,
        vad_speech_pad_ms=120,
        split_on_punctuation=False,
        device=1,
        use_gpu=True,
    )
    command = engine._build_command(
        tmp_path / "crispasr.exe",
        tmp_path / "large-v2-q8_0.bin",
        tmp_path / "input.wav",
        tmp_path / "output",
    )
    assert command[:3] == [str(tmp_path / "crispasr.exe"), "--backend", "whisper"]
    assert command[command.index("--language") + 1] == "ja"
    assert command[command.index("--threads") + 1] == "12"
    assert command[command.index("--device") + 1] == "1"
    assert "--vad" in command
    assert command[command.index("--vad-model") + 1] == "silero.bin"
    assert "--split-on-punct" not in command
    assert command[command.index("--vad-speech-pad-ms") + 1] == "120"
    assert "--max-len" not in command
    assert "--output-srt" in command


def test_whisper_command_can_force_cpu_and_disable_vad(tmp_path: Path) -> None:
    engine = CrispASREngine("crispasr.exe", "model.bin", vad_enabled=False, use_gpu=False)
    command = engine._build_command(
        tmp_path / "crispasr.exe",
        tmp_path / "model.bin",
        tmp_path / "input.wav",
        tmp_path / "output",
    )
    assert "--no-gpu" in command
    assert "--vad" not in command


@pytest.mark.parametrize("language", ["auto", "ja", "en"])
def test_whisper_uses_selected_language_and_keeps_supported_extra_args(tmp_path: Path, language: str) -> None:
    engine = CrispASREngine(
        "crispasr.exe",
        "model.bin",
        language=language,
        extra_args="--beam-size 5",
    )
    command = engine._build_command(
        tmp_path / "crispasr.exe",
        tmp_path / "model.bin",
        tmp_path / "input.wav",
        tmp_path / "output",
    )
    assert command[command.index("--backend") + 1] == "whisper"
    assert command[command.index("--language") + 1] == language
    assert command[-2:] == ["--beam-size", "5"]
    assert not {"--aligner-model", "--force-aligner", "--lid-model", "--lid-backend"}.intersection(command)
    assert "--max-new-tokens" not in command
    assert "--frequency-penalty" not in command
    assert "--vad-max-speech-duration-s" not in command


@pytest.mark.parametrize(
    "option,value",
    [
        ("--language", "ja"),
        ("-l", "ja"),
        ("--backend", "qwen3-1.7b"),
        ("--model", "other.gguf"),
        ("-m", "other.gguf"),
        ("--lid-model", "tiny.bin"),
        ("--lid-backend", "whisper"),
        ("--aligner-model", "aligner.gguf"),
        ("--hf-repo", "some/model"),
        ("-hfr", "some/model"),
    ],
)
@pytest.mark.parametrize("separator", [" ", "="])
def test_extra_args_cannot_override_whisper_or_load_removed_models(
    tmp_path: Path, option: str, value: str, separator: str
) -> None:
    for name in ("crispasr.exe", "model.bin", "input.wav"):
        (tmp_path / name).touch()
    engine = CrispASREngine(
        str(tmp_path / "crispasr.exe"),
        str(tmp_path / "model.bin"),
        extra_args=f"{option}{separator}{value}",
    )
    with patch("app.core.crispasr_engine.subprocess.Popen") as popen:
        with pytest.raises(ValueError, match="Whisper 模型和源语言"):
            engine.transcribe(str(tmp_path / "input.wav"))
        popen.assert_not_called()


@pytest.mark.parametrize("extra_args", ["--force-aligner", "--auto-download"])
def test_extra_args_cannot_enable_alignment_or_automatic_download(extra_args: str) -> None:
    engine = CrispASREngine("crispasr.exe", "model.bin", extra_args=extra_args)
    with pytest.raises(ValueError, match="Whisper 模型和源语言"):
        engine._build_command(Path("crispasr.exe"), Path("model.bin"), Path("input.wav"), Path("output"))
