from __future__ import annotations

import os
import subprocess
import sys


def test_utf8_stdio_bootstrap_makes_redirected_output_utf8() -> None:
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONIOENCODING", None)
    script = (
        "from app.common.text_encoding import configure_utf8_stdio; "
        "configure_utf8_stdio(); "
        "print('日本語测试')"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert result.stdout == f"日本語测试{os.linesep}".encode("utf-8")


def test_decode_process_output_preserves_utf8_and_windows_ansi() -> None:
    from app.common.text_encoding import decode_process_output

    value = "日本語测试"
    assert decode_process_output(value.encode("utf-8")) == value
    assert decode_process_output(value.encode("gb18030")) == value
    assert "�" not in decode_process_output(value.encode("gb18030"))
