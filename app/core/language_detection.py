"""Offline LID preflight, shared by the pipeline and the native ASR adapter."""
from pathlib import Path
import struct


def validate_lid_model(backend: str, language: str, model_path: str) -> Path | None:
    if backend != 'qwen3-1.7b' or language != 'auto':
        return None
    message = (
        'Qwen3-ASR 自动语言检测需要有效的本地多语言 Whisper 模型。'
        '请在转录设置中选择语言检测模型 ggml-tiny.bin，'
        '或在首页将源语言设为「日本語」等已知语言；不会自动联网下载。'
    )
    try:
        path = Path(model_path).expanduser()
        if not model_path.strip() or not path.is_file() or path.stat().st_size < 1024 * 1024:
            raise ValueError(message)
        with path.open('rb') as stream:
            magic, vocabulary = struct.unpack('<II', stream.read(8))
        if magic != 0x67676d6c or vocabulary < 51865:
            raise ValueError(message + ' 请选择多语言 .bin 模型，不要使用 .en 或 GGUF 模型。')
    except (OSError, struct.error) as exc:
        raise ValueError(message) from exc
    return path.resolve()
