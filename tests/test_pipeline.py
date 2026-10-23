from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppConfig
from app.core.pipeline import PipelineCancelled, ProcessingPipeline
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
        asr_whisper_model_path=str(asr_model),
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
        AppConfig(asr_whisper_model_path=str(model)),
        server_factory=lambda **kwargs: FakeServer(events, **kwargs),  # type: ignore[arg-type]
        crispasr_factory=lambda **kwargs: BrokenASR(events, **kwargs),  # type: ignore[arg-type]
    )
    task = ProcessingTask(input_files=[str(audio)], process_mode=ProcessMode.TRANSCRIBE_ONLY)
    with pytest.raises(RuntimeError, match="boom"):
        pipeline.run(task)
    assert events == ["start:asr:asr.gguf", "stop:asr"]


@pytest.mark.parametrize("source_language,expected", [("自动检测", "auto"), ("日本語", "ja"), ("English", "en")])
def test_pipeline_passes_whisper_settings_and_source_language(
    tmp_path: Path, source_language: str, expected: str
) -> None:
    audio = tmp_path / "sample.wav"
    model = tmp_path / "whisper.bin"
    audio.touch()
    model.touch()
    captured: dict[str, object] = {}

    class CapturingASR(FakeASR):
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def stop(self) -> None:
            pass

    pipeline = ProcessingPipeline(
        AppConfig(
            asr_whisper_model_path=str(model),
            asr_whisper_extra_args="--beam-size 5",
            asr_vad_enabled=False,
        ),
        crispasr_factory=CapturingASR,  # type: ignore[arg-type]
    )
    pipeline.run(
        ProcessingTask(input_files=[str(audio)], source_language=source_language, process_mode=ProcessMode.TRANSCRIBE_ONLY)
    )
    assert captured["model_path"] == str(model)
    assert captured["language"] == expected
    assert captured["extra_args"] == "--beam-size 5"
    assert captured["vad_enabled"] is False
    assert not {"backend", "aligner_model_path", "lid_model_path"}.intersection(captured)


def test_cancellation_between_files_unloads_asr_without_starting_translation(tmp_path: Path) -> None:
    audio = tmp_path / "sample.wav"
    next_audio = tmp_path / "next.wav"
    model = tmp_path / "whisper.bin"
    audio.touch()
    next_audio.touch()
    model.touch()
    events: list[str] = []

    class CancellingASR(FakeWhisper):
        def transcribe(self, path: str, timestamps: bool = True) -> list[TranscriptionSegment]:
            segments = super().transcribe(path, timestamps)
            pipeline.cancel()
            return segments

    pipeline = ProcessingPipeline(
        AppConfig(asr_whisper_model_path=str(model), translation_model_path="translate.gguf"),
        server_factory=lambda **kwargs: FakeServer(events, **kwargs),  # type: ignore[arg-type]
        crispasr_factory=lambda **kwargs: CancellingASR(events, **kwargs),  # type: ignore[arg-type]
    )
    task = ProcessingTask(input_files=[str(audio), str(next_audio)], process_mode=ProcessMode.TRANSCRIBE_AND_TRANSLATE)
    with pytest.raises(PipelineCancelled, match="任务已取消"):
        pipeline.run(task)
    assert events == ["start:asr:asr.gguf", "stop:asr"]
    assert pipeline._active_asr is None


def test_subtitle_only_task_does_not_require_asr_models(tmp_path: Path) -> None:
    subtitle = tmp_path / "sample.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

    def unexpected_asr(**_kwargs: object) -> None:
        raise AssertionError("Subtitle input must not start ASR")

    pipeline = ProcessingPipeline(AppConfig(), crispasr_factory=unexpected_asr)  # type: ignore[arg-type]
    outputs = pipeline.run(
        ProcessingTask(
            input_files=[str(subtitle)],
            output_directory=str(tmp_path / "out"),
            content_mode=ContentMode.SOURCE_ONLY,
            process_mode=ProcessMode.TRANSCRIBE_ONLY,
        )
    )
    assert "hello" in Path(outputs[0]).read_text(encoding="utf-8-sig")


def test_vocal_separation_finishes_before_asr_load(tmp_path: Path) -> None:
    audio = tmp_path / "mixed.wav"
    asr_model = tmp_path / "asr.gguf"
    separator_model = tmp_path / "uvr.onnx"
    audio.write_bytes(b"mixed")
    asr_model.touch()
    separator_model.touch()
    events: list[str] = []
    config = AppConfig(
        asr_whisper_model_path=str(asr_model),
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
