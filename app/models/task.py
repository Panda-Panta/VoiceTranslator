from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class FileType(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"
    SUBTITLE = "subtitle"
    LYRICS = "lyrics"


class ProcessMode(str, Enum):
    TRANSCRIBE_ONLY = "transcribe_only"
    TRANSCRIBE_AND_TRANSLATE = "transcribe_and_translate"


class ContentMode(str, Enum):
    BILINGUAL = "bilingual"
    SOURCE_ONLY = "source_only"
    TARGET_ONLY = "target_only"


class ExportFormat(str, Enum):
    SRT = ".srt"
    LRC = ".lrc"


@dataclass(slots=True)
class ProcessingTask:
    input_files: list[str]
    target_language: str = "简体中文"
    export_format: ExportFormat = ExportFormat.SRT
    content_mode: ContentMode = ContentMode.BILINGUAL
    process_mode: ProcessMode = ProcessMode.TRANSCRIBE_AND_TRANSLATE
    output_directory: str = ""
    source_language: str = "自动检测"
    file_type: FileType | None = None
    overwrite: bool = False
    metadata: dict[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.input_files:
            raise ValueError("请至少添加一个输入文件")
        missing = [path for path in self.input_files if not Path(path).is_file()]
        if missing:
            raise FileNotFoundError(f"找不到输入文件：{missing[0]}")
        if self.process_mode is ProcessMode.TRANSCRIBE_ONLY:
            self.content_mode = ContentMode.SOURCE_ONLY

    @property
    def output_path(self) -> Path:
        return Path(self.output_directory) if self.output_directory else Path(self.input_files[0]).parent
