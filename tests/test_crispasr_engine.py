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
