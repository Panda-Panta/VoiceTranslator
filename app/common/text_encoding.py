from __future__ import annotations

import locale
import os
import sys
from collections.abc import Iterable
from typing import BinaryIO, TextIO


UTF8 = "utf-8"


def configure_utf8_stdio() -> None:
    """Make this process and Python child processes use UTF-8 consistently."""
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = UTF8

    if os.name == "nt":
        _set_windows_console_code_page()

    _reconfigure_stream(sys.stdout)
    _reconfigure_stream(sys.stderr)


def decode_process_output(value: bytes | str) -> str:
    """Decode tool output without irreversibly replacing non-UTF-8 bytes."""
    if isinstance(value, str):
        return value
    for encoding in _candidate_encodings():
        try:
            return value.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return value.decode(UTF8, errors="backslashreplace")


def iter_decoded_lines(stream: BinaryIO | Iterable[bytes]) -> Iterable[str]:
    for line in stream:
        yield decode_process_output(line)


def _candidate_encodings() -> tuple[str, ...]:
    encodings = [UTF8]
    if os.name == "nt":
        encodings.extend(_windows_code_page_encodings())
    encodings.extend([locale.getpreferredencoding(False), "gb18030"])
    return tuple(dict.fromkeys(item for item in encodings if item))


def _windows_code_page_encodings() -> list[str]:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        return [f"cp{kernel32.GetACP()}", f"cp{kernel32.GetOEMCP()}"]
    except (AttributeError, OSError):
        return []


def _set_windows_console_code_page() -> None:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except (AttributeError, OSError):
        pass


def _reconfigure_stream(stream: TextIO | None) -> None:
    if stream is None or not hasattr(stream, "reconfigure"):
        return
    try:
        stream.reconfigure(encoding=UTF8, errors="backslashreplace")
    except (AttributeError, OSError, ValueError):
        pass


__all__ = ["configure_utf8_stdio", "decode_process_output", "iter_decoded_lines"]
