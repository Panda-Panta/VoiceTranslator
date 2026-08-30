from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from app.common.text_encoding import decode_process_output


class VocalSeparator:
    """Run the bundled UVR/MDX separator in an isolated process."""

    def __init__(
        self,
        model_path: str,
        log_callback: Callable[[str], None] | None = None,
        project_root: str | Path | None = None,
    ) -> None:
        self.model_path = Path(model_path).expanduser()
        self.log_callback = log_callback or (lambda _message: None)
        self.project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
        self.process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    def separate_many(self, audio_paths: list[str | Path]) -> list[Path]:
        self._validate_runtime()
        sources = [Path(path).resolve() for path in audio_paths]
        if not sources:
            return []
        missing = next((path for path in sources if not path.is_file()), None)
        if missing:
            raise FileNotFoundError(f"找不到待分离音频：{missing}")

        command = self._command(sources)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.log_callback(f"正在加载人声分离模型：{self.model_path.name}")
        try:
            with self._lock:
                self.process = subprocess.Popen(
                    command,
                    cwd=self.project_root,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
                process = self.process
            output_bytes, _ = process.communicate()
            output = decode_process_output(output_bytes)
            if output.strip():
                for line in output.splitlines():
                    self.log_callback(f"[人声分离] {line}")
            if process.returncode != 0:
                raise RuntimeError(f"人声分离进程退出码：{process.returncode}")
            results = [self._vocal_output(path) for path in sources]
            invalid = next((path for path in results if not path.is_file() or path.stat().st_size == 0), None)
            if invalid:
                raise RuntimeError(f"人声分离未生成有效的人声轨：{invalid}")
            return results
        finally:
            with self._lock:
                self.process = None
            self.log_callback("人声分离进程已停止，分离模型内存已释放")

    def _command(self, sources: list[Path]) -> list[str]:
        if getattr(sys, "frozen", False):
            executable = self.project_root / "separate" / ("separate.exe" if os.name == "nt" else "separate")
            if not executable.is_file():
                raise FileNotFoundError(f"找不到人声分离程序：{executable}")
            return [str(executable), "-m", str(self.model_path), "--model-target", "vocals", *(str(path) for path in sources)]
        script = self.project_root / "separate.py"
        if not script.is_file():
            raise FileNotFoundError(f"找不到人声分离脚本：{script}")
        return [sys.executable, str(script), "-m", str(self.model_path), "--model-target", "vocals", *(str(path) for path in sources)]

    def _vocal_output(self, source: Path) -> Path:
        # Kim Vocal 2 directly predicts vocals. The runner normalizes that
        # direct model output to `_vocals` for the ASR stage.
        return Path(str(source) + "_vocals.wav")

    def _validate_runtime(self) -> None:
        if not self.model_path.is_file() or self.model_path.suffix.lower() != ".onnx":
            raise FileNotFoundError(f"找不到有效的 UVR/MDX ONNX 模型：{self.model_path}")

    def stop(self) -> None:
        with self._lock:
            process = self.process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
