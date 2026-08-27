from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from shutil import which

from app.core.subtitle_parser import SubtitleParser
from app.models import TranscriptionSegment


class CrispASREngine:
    """Run Whisper in a short-lived CrispASR process.

    The child process owns the model. Its exit is the unload barrier for RAM
    and VRAM on success, failure, and cancellation.
    """

    def __init__(
        self,
        executable: str,
        model_path: str,
        *,
        threads: int = 4,
        language: str = "auto",
        vad_enabled: bool = True,
        vad_model_path: str = "",
        vad_min_silence_ms: int = 500,
        vad_speech_pad_ms: int = 150,
        split_on_punctuation: bool = False,
        device: int = 0,
        use_gpu: bool = True,
        extra_args: str = "",
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.executable = executable
        self.model_path = model_path
        self.threads = max(1, threads)
        self.language = language or "auto"
        self.vad_enabled = vad_enabled
        self.vad_model_path = vad_model_path
        self.vad_min_silence_ms = max(0, vad_min_silence_ms)
        self.vad_speech_pad_ms = max(0, vad_speech_pad_ms)
        self.split_on_punctuation = split_on_punctuation
        self.device = max(0, device)
        self.use_gpu = use_gpu
        self.extra_args = extra_args
        self.log_callback = log_callback or (lambda _message: None)
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def transcribe(self, audio_path: str, timestamps: bool = True) -> list[TranscriptionSegment]:
        source = Path(audio_path)
        if not source.is_file():
            raise FileNotFoundError(f"找不到音频文件：{source}")
        executable = self._resolve_executable()
        model = Path(self.model_path)
        if not model.is_file():
            raise FileNotFoundError(f"找不到 Whisper 模型：{model}")

        with tempfile.TemporaryDirectory(prefix="voice_translator_whisper_") as temp_dir:
            output_base = Path(temp_dir) / "transcript"
            command = self._build_command(executable, model, source, output_base)
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creationflags,
                )
            except OSError as exc:
                raise RuntimeError(f"无法启动 CrispASR：{executable}") from exc
            with self._lock:
                self._process = process
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    message = line.rstrip()
                    if message:
                        self.log_callback(f"[Whisper] {message}")
                code = process.wait()
            finally:
                with self._lock:
                    self._process = None
            if code != 0:
                raise RuntimeError(f"Whisper 转录失败，CrispASR 退出码 {code}")

            output = self._find_output(output_base)
            if output is None:
                raise RuntimeError("Whisper 未生成 SRT 字幕文件")
            segments = SubtitleParser().parse_srt(output)
            for segment in segments:
                segment.text = re.sub(r"[ \t]{2,}", " ", segment.text).strip()
            if not timestamps:
                for segment in segments:
                    segment.start_time = 0.0
                    segment.end_time = 0.0
            return segments

    def stop(self) -> None:
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _resolve_executable(self) -> Path:
        candidate = Path(self.executable)
        if candidate.is_file():
            return candidate
        resolved = which(self.executable)
        if resolved:
            return Path(resolved)
        raise FileNotFoundError(f"找不到 CrispASR：{self.executable}")

    def _build_command(self, executable: Path, model: Path, source: Path, output_base: Path) -> list[str]:
        command = [
            str(executable),
            "--backend",
            "whisper",
            "--model",
            str(model),
            "--file",
            str(source),
            "--language",
            self.language,
            "--threads",
            str(self.threads),
            "--output-srt",
            "--output-file",
            str(output_base),
        ]
        if self.vad_enabled:
            command.extend(["--vad", "--vad-min-silence-duration-ms", str(self.vad_min_silence_ms)])
            command.extend(["--vad-speech-pad-ms", str(self.vad_speech_pad_ms)])
            if self.vad_model_path:
                command.extend(["--vad-model", self.vad_model_path])
        if self.split_on_punctuation:
            command.append("--split-on-punct")
        command.extend(["--device", str(self.device)] if self.use_gpu else ["--no-gpu"])
        command.extend(self._split_extra_args(self.extra_args))
        return command

    @staticmethod
    def _find_output(base: Path) -> Path | None:
        candidates = (base.with_suffix(".srt"), base, Path(f"{base}.srt"))
        return next((path for path in candidates if path.is_file()), None)

    @staticmethod
    def _split_extra_args(value: str) -> list[str]:
        if not value.strip():
            return []
        return [item.strip('"') for item in shlex.split(value, posix=False)]


__all__ = ["CrispASREngine"]
