from __future__ import annotations

import shutil
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import AppConfig, resolve_whisper_runtime
from app.core.crispasr_engine import CrispASREngine
from app.core.file_handler import FileHandler
from app.core.llama_server_manager import LlamaServerManager
from app.core.subtitle_parser import SubtitleParser
from app.core.subtitle_segmenter import SubtitleSegmenter
from app.core.translator import LocalTranslator, OnlineTranslator, TranslatorBase
from app.core.vocal_separator import VocalSeparator
from app.models import ExportFormat, FileType, ProcessingTask, TranscriptionSegment


class PipelineCancelled(RuntimeError):
    pass


@dataclass(slots=True)
class _WorkItem:
    source: Path
    file_type: FileType
    segments: list[TranscriptionSegment] | None = None
    audio_path: Path | None = None


class ProcessingPipeline:
    """Strict three-stage pipeline: transcribe all, unload, translate all, unload."""

    def __init__(
        self,
        config: AppConfig,
        progress_callback: Callable[[int, str], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
        completed_callback: Callable[[list[str]], None] | None = None,
        failed_callback: Callable[[str], None] | None = None,
        server_factory: Callable[..., LlamaServerManager] = LlamaServerManager,
        crispasr_factory: Callable[..., CrispASREngine] = CrispASREngine,
        translator_factory: Callable[..., TranslatorBase] | None = None,
        separator_factory: Callable[..., VocalSeparator] = VocalSeparator,
    ) -> None:
        self.config = config
        self.on_progress = progress_callback or (lambda _percent, _message: None)
        self.on_log = log_callback or (lambda _message: None)
        self.on_completed = completed_callback or (lambda _outputs: None)
        self.on_failed = failed_callback or (lambda _message: None)
        self.server_factory = server_factory
        self.crispasr_factory = crispasr_factory
        self.translator_factory = translator_factory
        self.separator_factory = separator_factory
        self._cancelled = threading.Event()
        self._active_servers: list[LlamaServerManager] = []
        self._active_separator: VocalSeparator | None = None
        self._active_asr: CrispASREngine | None = None

    def cancel(self) -> None:
        self._cancelled.set()
        for server in tuple(self._active_servers):
            server.stop()
        if self._active_separator is not None:
            self._active_separator.stop()
        if self._active_asr is not None:
            self._active_asr.stop()

    def _check_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise PipelineCancelled("任务已取消")

    def run(self, task: ProcessingTask) -> list[str]:
        self._cancelled.clear()
        try:
            outputs = self._execute(task)
        except PipelineCancelled as exc:
            self.on_log(str(exc))
            self.on_failed(str(exc))
            raise
        except Exception as exc:
            self.on_log(f"处理失败：{exc}")
            self.on_failed(str(exc))
            raise
        else:
            self.on_progress(100, "全部处理完成")
            self.on_completed(outputs)
            return outputs
        finally:
            # Last-resort cleanup: no model survives success, failure, or cancellation.
            for server in tuple(self._active_servers):
                server.stop()
            self._active_servers.clear()
            if self._active_separator is not None:
                self._active_separator.stop()
                self._active_separator = None
            if self._active_asr is not None:
                self._active_asr.stop()
                self._active_asr = None

    def _execute(self, task: ProcessingTask) -> list[str]:
        task.validate()
        handler = FileHandler(self.config.ffmpeg_path)
        parser = SubtitleParser()
        items = [_WorkItem(Path(path), handler.detect_type(path)) for path in task.input_files]
        self.on_progress(2, "正在准备文件")

        with tempfile.TemporaryDirectory(prefix="voice_translator_") as temp_dir:
            temp_root = Path(temp_dir)
            for position, item in enumerate(items, 1):
                self._check_cancelled()
                if item.file_type is FileType.SUBTITLE:
                    item.segments = parser.parse_srt(item.source)
                    self.on_log(f"已解析字幕：{item.source.name}")
                elif item.file_type is FileType.LYRICS:
                    item.segments = parser.parse_lrc(item.source)
                    self.on_log(f"已解析歌词：{item.source.name}")
                elif item.file_type is FileType.VIDEO:
                    audio = temp_root / f"{position}_{item.source.stem}.wav"
                    separation = self.config.vocal_separation_enabled
                    item.audio_path = Path(
                        handler.extract_audio(
                            item.source,
                            audio,
                            sample_rate=44100 if separation else 16000,
                            channels=2 if separation else 1,
                        )
                    )
                    self.on_log(f"已提取音频：{item.source.name}")
                else:
                    item.audio_path = item.source

            media_items = [item for item in items if item.audio_path is not None]
            if media_items and self.config.vocal_separation_enabled:
                self._separate_vocals(media_items, temp_root)
            if media_items:
                self._transcribe_all(media_items, task.source_language)
            self.on_progress(55, "转录阶段完成，ASR 模型已卸载")

            if task.process_mode.value == "transcribe_and_translate":
                self._translate_all(items, task.source_language, task.target_language)
                self.on_progress(90, "翻译阶段完成，翻译模型已卸载")

            outputs = self._export_all(items, task, parser)
            return outputs

    def _separate_vocals(self, items: list[_WorkItem], temp_root: Path) -> None:
        if not self.config.vocal_separation_model_path:
            raise ValueError("已启用自动人声分离，但尚未选择官方 UVR/MDX ONNX 模型")
        staged_paths: list[Path] = []
        for index, item in enumerate(items, 1):
            assert item.audio_path is not None
            suffix = item.audio_path.suffix or ".wav"
            staged = temp_root / f"separation_{index}{suffix}"
            if item.audio_path.resolve() != staged.resolve():
                shutil.copy2(item.audio_path, staged)
            staged_paths.append(staged)
        separator = self.separator_factory(
            model_path=self.config.vocal_separation_model_path,
            log_callback=self.on_log,
        )
        self._active_separator = separator
        self.on_progress(5, "正在分离人声与背景音")
        try:
            outputs = separator.separate_many(staged_paths)
        except RuntimeError:
            self._check_cancelled()
            raise
        finally:
            separator.stop()
            self._active_separator = None
        self._check_cancelled()
        for item, output in zip(items, outputs, strict=True):
            item.audio_path = output
            self.on_log(f"已生成人声轨：{item.source.name}")
        self.on_progress(12, "人声分离完成，分离模型已卸载")

    def _new_server(self) -> LlamaServerManager:
        server = self.server_factory(
            executable=self.config.llama_server_path,
            log_callback=self.on_log,
        )
        self._active_servers.append(server)
        return server

    def _transcribe_all(self, items: list[_WorkItem], source_language: str = "自动检测") -> None:
        resolve_whisper_runtime(self.config)
        if not self.config.asr_model_path:
            raise ValueError("未找到 Whisper 模型，请运行 tools/setup_whisper_runtime.ps1")
        self._transcribe_all_whisper(items, source_language)

    def _transcribe_all_whisper(self, items: list[_WorkItem], source_language: str) -> None:
        engine = self.crispasr_factory(
            executable=self.config.crispasr_path,
            model_path=self.config.asr_model_path,
            threads=self.config.asr_threads,
            language=self._asr_language(source_language),
            vad_enabled=self.config.asr_vad_enabled,
            vad_model_path=self.config.asr_vad_model_path,
            vad_min_silence_ms=self.config.asr_vad_min_silence_ms,
            vad_speech_pad_ms=self.config.asr_vad_speech_pad_ms,
            split_on_punctuation=self.config.asr_split_on_punctuation,
            device=self.config.asr_device,
            use_gpu=self.config.asr_gpu_layers != 0,
            extra_args=self.config.asr_extra_args,
            log_callback=self.on_log,
        )
        self._active_asr = engine
        self.on_progress(15, "正在加载 Whisper 模型")
        try:
            for index, item in enumerate(items, 1):
                self._check_cancelled()
                self.on_log(f"正在使用 Whisper 转录：{item.source.name}")
                item.segments = engine.transcribe(str(item.audio_path), timestamps=True)
                if not item.segments:
                    raise RuntimeError(f"转录结果为空：{item.source.name}")
                if self.config.subtitle_resegment_enabled:
                    item.segments = SubtitleSegmenter(
                        max_chars=self.config.subtitle_max_chars,
                        max_duration=self.config.subtitle_max_duration,
                        merge_gap_ms=self.config.subtitle_merge_gap_ms,
                    ).resegment(item.segments)
                    self.on_log(f"已重排字幕断句：{item.source.name}（{len(item.segments)} 条）")
                percent = 17 + round(index / len(items) * 35)
                self.on_progress(percent, f"已完成转录 {index}/{len(items)}")
        finally:
            engine.stop()
            self._active_asr = None

    @staticmethod
    def _asr_language(value: str) -> str:
        return {
            "自动检测": "auto",
            "简体中文": "zh",
            "English": "en",
            "日本語": "ja",
            "한국어": "ko",
            "Français": "fr",
            "Deutsch": "de",
            "Español": "es",
            "Русский": "ru",
        }.get(value, value or "auto")

    def _translator(self, server: LlamaServerManager | None) -> TranslatorBase:
        common = {
            "batch_size": self.config.batch_size,
            "temperature": self.config.temperature,
            "system_prompt": self.config.translation_prompt,
        }
        if self.translator_factory:
            return self.translator_factory(server=server, config=self.config, **common)
        if self.config.translation_engine == "local":
            assert server is not None
            return LocalTranslator(base_url=server.base_url, **common)
        if not self.config.api_key or not self.config.api_model:
            raise ValueError("请先配置在线 API Key 和模型名称")
        return OnlineTranslator(
            base_url=self.config.api_base_url,
            api_key=self.config.api_key,
            model=self.config.api_model,
            **common,
        )

    def _translate_all(self, items: list[_WorkItem], source_language: str, target_language: str) -> None:
        server: LlamaServerManager | None = None
        try:
            if self.config.translation_engine == "local":
                if not self.config.translation_model_path:
                    raise ValueError("请先在翻译设置中选择本地翻译模型")
                server = self._new_server()
                self.on_progress(57, "正在加载翻译模型")
                server.start(
                    model_path=self.config.translation_model_path,
                    port=self.config.translation_port,
                    n_gpu_layers=self.config.translation_gpu_layers,
                    ctx_size=self.config.translation_context_size,
                    timeout=self.config.server_start_timeout,
                )
            translator = self._translator(server)
            total = sum(len(item.segments or []) for item in items)
            completed = 0
            for item in items:
                self._check_cancelled()
                segments = item.segments or []
                self.on_log(f"正在翻译：{item.source.name}")

                def update(done: int, _count: int, base: int = completed) -> None:
                    self._check_cancelled()
                    ratio = (base + done) / max(1, total)
                    self.on_progress(60 + round(ratio * 28), f"翻译进度 {base + done}/{total}")

                translator.translate(segments, source_language, target_language, update)
                completed += len(segments)
        finally:
            if server is not None:
                server.stop()
                if server in self._active_servers:
                    self._active_servers.remove(server)

    def _export_all(self, items: list[_WorkItem], task: ProcessingTask, parser: SubtitleParser) -> list[str]:
        output_dir = task.output_path
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs = []
        for index, item in enumerate(items, 1):
            target = output_dir / f"{item.source.stem}{task.export_format.value}"
            if target.exists() and not task.overwrite:
                target = self._unique_path(target)
            segments = item.segments or []
            if task.export_format is ExportFormat.SRT:
                outputs.append(parser.export_srt(segments, task.content_mode, target))
            else:
                outputs.append(parser.export_lrc(segments, task.content_mode, target))
            self.on_log(f"已导出：{target}")
            self.on_progress(90 + round(index / len(items) * 9), f"正在导出 {index}/{len(items)}")
        return outputs

    @staticmethod
    def _unique_path(path: Path) -> Path:
        for number in range(1, 10_000):
            candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"无法为输出文件分配名称：{path}")
