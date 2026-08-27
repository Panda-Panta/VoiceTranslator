from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


STORED_SUFFIXES = {".bin", ".gguf", ".onnx"}


def create_archive(source: Path, output: Path) -> None:
    files = sorted(path for path in source.rglob("*") if path.is_file())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    total = sum(path.stat().st_size for path in files)
    completed = 0
    with zipfile.ZipFile(output, "w", allowZip64=True) as archive:
        for index, path in enumerate(files, 1):
            relative = Path(source.name) / path.relative_to(source)
            compression = zipfile.ZIP_STORED if path.suffix.lower() in STORED_SUFFIXES else zipfile.ZIP_DEFLATED
            archive.write(path, relative.as_posix(), compress_type=compression, compresslevel=6)
            completed += path.stat().st_size
            print(f"[{index}/{len(files)}] {completed / total:6.1%} {relative}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a ZIP64 VoiceTranslator portable archive")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    create_archive(args.source.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
