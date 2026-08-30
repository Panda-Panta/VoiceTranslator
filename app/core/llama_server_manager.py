from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

import requests

from app.common.text_encoding import iter_decoded_lines


class LlamaServerManager:
    """Owns one llama-server process and guarantees deterministic model unloading."""

    def __init__(
        self,
        executable: str = "llama-server",
        host: str = "127.0.0.1",
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.executable = executable
        self.host = host
        self.log_callback = log_callback or (lambda _message: None)
        self.process: subprocess.Popen[bytes] | None = None
        self.port: int | None = None
        self._reader: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self.port is None:
            raise RuntimeError("llama-server 尚未启动")
        return f"http://{self.host}:{self.port}"

    def start(
        self,
        model_path: str,
        port: int,
        n_gpu_layers: int = 999,
        ctx_size: int = 8192,
        n_threads: int | None = None,
        extra_args: str = "",
        timeout: float = 120.0,
    ) -> bool:
        if self.is_running():
            if self.port == port and self.health_check():
                return True
            self.stop()
        model = Path(model_path).expanduser()
        if not model.is_file():
            raise FileNotFoundError(f"找不到模型文件：{model}")
        command = [
            self.executable,
            "--model",
            str(model),
            "--host",
            self.host,
            "--port",
            str(port),
            "--n-gpu-layers",
            str(n_gpu_layers),
            "--ctx-size",
            str(ctx_size),
        ]
        if n_threads:
            command.extend(["--threads", str(n_threads)])
        if extra_args.strip():
            extra_tokens = shlex.split(extra_args, posix=os.name != "nt")
            command.extend(extra_tokens)
        self.log_callback(f"启动模型服务：{Path(self.executable).name}，模型={model.name}")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        except FileNotFoundError as exc:
            self.process = None
            raise RuntimeError(f"未找到 llama-server：{self.executable}") from exc
        self.port = port
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                code = self.process.returncode
                self.stop()
                raise RuntimeError(f"llama-server 启动失败，退出码 {code}")
            if self.health_check(timeout=1.0):
                return True
            time.sleep(0.4)
        self.stop()
        raise TimeoutError(f"llama-server 在 {timeout:g} 秒内未就绪")

    def _read_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in iter_decoded_lines(process.stdout):
            message = line.rstrip()
            if message:
                self.log_callback(f"[llama-server] {message}")

    def health_check(self, timeout: float = 2.0) -> bool:
        if not self.is_running() or self.port is None:
            return False
        try:
            response = requests.get(f"{self.base_url}/health", timeout=timeout)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self, timeout: float = 8.0) -> None:
        """Stop the process; exiting llama-server releases the loaded GGUF model."""
        process, self.process = self.process, None
        self.port = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stdout:
            process.stdout.close()
        self.log_callback("模型服务已停止，模型内存已释放")

    def __enter__(self) -> "LlamaServerManager":
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop()

    def __del__(self) -> None:
        try:
            self.stop(timeout=1)
        except Exception:
            pass
