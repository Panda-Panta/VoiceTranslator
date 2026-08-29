from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppConfig
from app.core.pipeline import ProcessingPipeline
from app.models import ContentMode, ExportFormat, ProcessMode, ProcessingTask, TranscriptionSegment


class FakeServer:
    def __init__(self, events: list[str], **_kwargs: object) -> None:
        self.events = events
        self.kind = "unknown"
        self.port = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, model_path: str, port: int, **_kwargs: object) -> bool:
        self.kind = "asr" if port == 8081 else "translation"
        self.port = port
        self.events.append(f"start:{self.kind}:{Path(model_path).name}")
        return True

    def stop(self, **_kwargs: object) -> None:
        if self.kind != "unknown":
            self.events.append(f"stop:{self.kind}")
            self.kind = "unknown"


class FakeASR:
    def __init__(self, **_kwargs: object) -> None:
        pass

    def transcribe(self, _path: str, timestamps: bool = True) -> list[TranscriptionSegment]:
        assert timestamps
        return [TranscriptionSegment(1, 0, 1, "hello")]


class FakeWhisper:
    def __init__(self, events: list[str], **_kwargs: object) -> None:
        self.events = events
        self.started = False

    def transcribe(self, _path: str, timestamps: bool = True) -> list[TranscriptionSegment]:
        assert timestamps
        if not self.started:
            self.events.append("start:asr:asr.gguf")
            self.started = True
        return [TranscriptionSegment(1, 0, 1, "hello")]

    def stop(self) -> None:
        if self.started:
            self.events.append("stop:asr")
            self.started = False


class FakeTranslator:
    def translate(self, segments, _source, _target, progress_callback=None):  # type: ignore[no-untyped-def]
        for segment in segments:
            segment.translated_text = "你好"
        if progress_callback:
            progress_callback(len(segments), len(segments))
        return segments


class FakeSeparator:
    def __init__(self, events: list[str], **_kwargs: object) -> None:
        self.events = events

    def separate_many(self, paths):  # type: ignore[no-untyped-def]
        self.events.append("separate:start")
        outputs = []
        for path in paths:
            output = Path(str(path) + "_vocals.wav")
            output.write_bytes(b"voice")
            outputs.append(output)
        return outputs

    def stop(self) -> None:
        self.events.append("separate:stop")


def test_pipeline_unloads_asr_before_loading_translation(tmp_path: Path) -> None:
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"fake audio")
    asr_model = tmp_path / "asr.gguf"
    translation_model = tmp_path / "translate.gguf"
    asr_model.touch()
    translation_model.touch()
    events: list[str] = []

    config = AppConfig(
        asr_model_path=str(asr_model),
        translation_model_path=str(translation_model),
        translation_engine="local",
    )
    pipeline = ProcessingPipeline(
        config,
        server_factory=lambda **kwargs: FakeServer(events, **kwargs),  # type: ignore[arg-type]
        crispasr_factory=lambda **kwargs: FakeWhisper(events, **kwargs),  # type: ignore[arg-type]
        translator_factory=lambda **_kwargs: FakeTranslator(),
    )
    outputs = pipeline.run(
        ProcessingTask(
            input_files=[str(audio)],
            output_directory=str(tmp_path / "out"),
            export_format=ExportFormat.SRT,
            content_mode=ContentMode.BILINGUAL,
            process_mode=ProcessMode.TRANSCRIBE_AND_TRANSLATE,
        )
    )
    assert events == [
        "start:asr:asr.gguf",
        "stop:asr",
        "start:translation:translate.gguf",
        "stop:translation",
    ]
    assert "hello\n你好" in Path(outputs[0]).read_text(encoding="utf-8-sig")


def test_pipeline_unloads_model_when_asr_raises(tmp_path: Path) -> None:
    audio = tmp_path / "bad.wav"
    model = tmp_path / "asr.gguf"
    audio.touch()
    model.touch()
    events: list[str] = []

    class BrokenASR(FakeWhisper):
        def transcribe(self, _path: str, timestamps: bool = True):  # type: ignore[no-untyped-def]
            self.events.append("start:asr:asr.gguf")
            self.started = True
            raise RuntimeError("boom")

    pipeline = ProcessingPipeline(
        AppConfig(asr_model_path=str(model)),
        server_factory=lambda **kwargs: FakeServer(events, **kwargs),  # type: ignore[arg-type]
        crispasr_factory=lambda **kwargs: BrokenASR(events, **kwargs),  # type: ignore[arg-type]
    )
    task = ProcessingTask(input_files=[str(audio)], process_mode=ProcessMode.TRANSCRIBE_ONLY)
    with pytest.raises(RuntimeError, match="boom"):
        pipeline.run(task)
    assert events == ["start:asr:asr.gguf", "stop:asr"]


def test_pipeline_passes_qwen3_backend_and_aligner(tmp_path: Path) -> None:
    audio = tmp_path / "sample.wav"
    model = tmp_path / "qwen3-asr.gguf"
    aligner = tmp_path / "qwen3-forced-aligner.gguf"
    audio.touch()
    model.touch()
    aligner.touch()
    captured: dict[str, object] = {}

    class CapturingASR(FakeASR):
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def stop(self) -> None:
            pass

    pipeline = ProcessingPipeline(
        AppConfig(
            asr_backend="qwen3-1.7b",
            asr_model_path=str(model),
            asr_aligner_model_path=str(aligner),
            asr_vad_enabled=False,
        ),
        crispasr_factory=CapturingASR,  # type: ignore[arg-type]
    )
    pipeline.run(ProcessingTask(input_files=[str(audio)], process_mode=ProcessMode.TRANSCRIBE_ONLY))
    assert captured["backend"] == "qwen3-1.7b"
    assert captured["aligner_model_path"] == str(aligner)


def test_vocal_separation_finishes_before_asr_load(tmp_path: Path) -> None:
    audio = tmp_path / "mixed.wav"
    asr_model = tmp_path / "asr.gguf"
    separator_model = tmp_path / "uvr.onnx"
    audio.write_bytes(b"mixed")
    asr_model.touch()
    separator_model.touch()
    events: list[str] = []
    config = AppConfig(
        asr_model_path=str(asr_model),
        vocal_separation_enabled=True,
        vocal_separation_model_path=str(separator_model),
    )
    pipeline = ProcessingPipeline(
        config,
        server_factory=lambda **kwargs: FakeServer(events, **kwargs),  # type: ignore[arg-type]
        crispasr_factory=lambda **kwargs: FakeWhisper(events, **kwargs),  # type: ignore[arg-type]
        separator_factory=lambda **kwargs: FakeSeparator(events, **kwargs),  # type: ignore[arg-type]
    )
    pipeline.run(
        ProcessingTask(
            input_files=[str(audio)],
            output_directory=str(tmp_path / "out"),
            process_mode=ProcessMode.TRANSCRIBE_ONLY,
        )
    )
    assert events == ["separate:start", "separate:stop", "start:asr:asr.gguf", "stop:asr"]
