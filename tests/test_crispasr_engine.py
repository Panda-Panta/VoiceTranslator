from pathlib import Path

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


def test_qwen3_command_uses_forced_aligner_and_qwen_defaults(tmp_path: Path) -> None:
    engine = CrispASREngine(
        "crispasr.exe",
        "qwen3-asr.gguf",
        backend="qwen3-1.7b",
        aligner_model_path="qwen3-forced-aligner.gguf",
        language="ja",
        vad_enabled=True,
        vad_model_path="silero.bin",
    )
    command = engine._build_command(
        tmp_path / "crispasr.exe",
        tmp_path / "qwen3-asr.gguf",
        tmp_path / "input.wav",
        tmp_path / "output",
    )
    assert command[:3] == [str(tmp_path / "crispasr.exe"), "--backend", "qwen3-1.7b"]
    assert command[command.index("--aligner-model") + 1] == "qwen3-forced-aligner.gguf"
    assert "--force-aligner" in command
    assert command[command.index("--max-new-tokens") + 1] == "96"
    assert command[command.index("--frequency-penalty") + 1] == "0.8"
    assert command[command.index("--vad-max-speech-duration-s") + 1] == "12"
