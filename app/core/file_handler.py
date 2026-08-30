from __future__ import annotations

import subprocess
from pathlib import Path

from app.common.constants import AUDIO_EXTENSIONS, LYRICS_EXTENSIONS, SUBTITLE_EXTENSIONS, VIDEO_EXTENSIONS
from app.common.text_encoding import decode_process_output
from app.models import FileType


class UnsupportedFileTypeError(ValueError):
    pass


class FileHandler:
    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        self.ffmpeg_path = ffmpeg_path

    def detect_type(self, file_path: str | Path) -> FileType:
        suffix = Path(file_path).suffix.lower()
        if suffix in AUDIO_EXTENSIONS:
            return FileType.AUDIO
        if suffix in VIDEO_EXTENSIONS:
            return FileType.VIDEO
        if suffix in SUBTITLE_EXTENSIONS:
            return FileType.SUBTITLE
        if suffix in LYRICS_EXTENSIONS:
            return FileType.LYRICS
        raise UnsupportedFileTypeError(f"不支持的文件格式：{suffix or '无扩展名'}")

    def needs_transcription(self, file_type: FileType) -> bool:
        return file_type in {FileType.AUDIO, FileType.VIDEO}

    def extract_audio(
        self,
        video_path: str | Path,
        output_path: str | Path,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> str:
        source, target = Path(video_path), Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(target),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True)
        except FileNotFoundError as exc:
            raise RuntimeError(f"未找到 FFmpeg：{self.ffmpeg_path}") from exc
        except subprocess.CalledProcessError as exc:
            raw_message = exc.stderr or exc.stdout
            message = decode_process_output(raw_message).strip() if raw_message else str(exc)
            raise RuntimeError(f"FFmpeg 音频提取失败：{message}") from exc
        if not target.is_file() or target.stat().st_size == 0:
            raise RuntimeError("FFmpeg 未生成有效音频文件")
        return str(target)
