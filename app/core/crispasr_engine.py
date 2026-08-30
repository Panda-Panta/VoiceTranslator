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

from app.common.text_encoding import iter_decoded_lines
from app.core.subtitle_parser import SubtitleParser
from app.models import TranscriptionSegment


class CrispASREngine:
    """Run Whisper or Qwen3-ASR in a short-lived CrispASR process.

    The child process owns the model. Its exit is the unload barrier for RAM
    and VRAM on success, failure, and cancellation.
    """

    def __init__(
        self,
        executable: str,
        model_path: str,
        *,
        backend: str = "whisper",
        aligner_model_path: str = "",
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
        self.backend = backend.strip() or "whisper"
        if self.backend not in {"whisper", "qwen3-1.7b"}:
            raise ValueError(f"不支持的 CrispASR 后端：{self.backend}")
        self.aligner_model_path = aligner_model_path
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
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    def transcribe(self, audio_path: str, timestamps: bool = True) -> list[TranscriptionSegment]:
        source = Path(audio_path)
        if not source.is_file():
            raise FileNotFoundError(f"找不到音频文件：{source}")
        executable = self._resolve_executable()
        model = Path(self.model_path)
        if not model.is_file():
            raise FileNotFoundError(f"找不到 {self.display_name} 模型：{model}")
        if self.is_qwen3:
            aligner = Path(self.aligner_model_path)
            if not aligner.is_file():
                raise FileNotFoundError(f"找不到 Qwen3 Forced Aligner 模型：{aligner}")

        with tempfile.TemporaryDirectory(prefix="voice_translator_asr_") as temp_dir:
            output_base = Path(temp_dir) / "transcript"
            command = self._build_command(executable, model, source, output_base)
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            except OSError as exc:
                raise RuntimeError(f"无法启动 CrispASR：{executable}") from exc
            with self._lock:
                self._process = process
            try:
                assert process.stdout is not None
                for line in iter_decoded_lines(process.stdout):
                    message = line.rstrip()
                    if message:
                        self.log_callback(f"[{self.display_name}] {message}")
                code = process.wait()
            finally:
                with self._lock:
                    self._process = None
            if code != 0:
                raise RuntimeError(f"{self.display_name} 转录失败，CrispASR 退出码 {code}")

            output = self._find_output(output_base)
            if output is None:
                raise RuntimeError(f"{self.display_name} 未生成 SRT 字幕文件")
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

    @property
    def is_qwen3(self) -> bool:
        return self.backend == "qwen3-1.7b"

    @property
    def display_name(self) -> str:
        return "Qwen3-ASR" if self.is_qwen3 else "Whisper"

    def _build_command(self, executable: Path, model: Path, source: Path, output_base: Path) -> list[str]:
        command = [
            str(executable),
            "--backend",
            self.backend,
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
        if self.is_qwen3:
            command.extend(
                [
                    "--aligner-model",
                    self.aligner_model_path,
                    "--force-aligner",
                    "--max-new-tokens",
                    "96",
                    "--frequency-penalty",
                    "0.8",
                ]
            )
        if self.vad_enabled:
            command.extend(["--vad", "--vad-min-silence-duration-ms", str(self.vad_min_silence_ms)])
            command.extend(["--vad-speech-pad-ms", str(self.vad_speech_pad_ms)])
            if self.vad_model_path:
                command.extend(["--vad-model", self.vad_model_path])
            if self.is_qwen3:
                command.extend(["--vad-max-speech-duration-s", "12"])
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
