from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ConfigStore


def main() -> int:
    config = ConfigStore().load()
    executable = Path(config.crispasr_path)
    model = Path(config.asr_model_path)
    vad = Path(config.asr_vad_model_path)
    for label, path in (("CrispASR", executable), ("Whisper", model), ("Silero VAD", vad)):
        if not path.is_file():
            raise FileNotFoundError(f"{label} 文件不存在：{path}")
        print(f"{label}: {path} ({path.stat().st_size:,} bytes)")
    result = subprocess.run(
        [str(executable), "--list-backends"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0 or "whisper" not in output.lower():
        raise RuntimeError(f"CrispASR Whisper 后端验证失败（退出码 {result.returncode}）")
    print("Whisper backend: OK")
    print("Default ASR backend: whisper")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
