from pathlib import Path

from app.core.vocal_separator import VocalSeparator


def test_direct_vocal_model_uses_normalized_vocal_stem(tmp_path: Path) -> None:
    separator = VocalSeparator("model.onnx", project_root=tmp_path)
    source = tmp_path / "audio.wav"
    assert separator._vocal_output(source) == Path(str(source) + "_vocals.wav")


def test_development_command_uses_bundled_script(tmp_path: Path) -> None:
    script = tmp_path / "separate.py"
    script.touch()
    model = tmp_path / "model.onnx"
    separator = VocalSeparator(str(model), project_root=tmp_path)
    command = separator._command([tmp_path / "audio.wav"])
    assert command[1:4] == [str(script), "-m", str(model)]
    assert command[4:6] == ["--model-target", "vocals"]
