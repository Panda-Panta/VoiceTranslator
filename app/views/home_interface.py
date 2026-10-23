from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SegmentedWidget,
    SubtitleLabel,
    TextEdit,
)

from app.common.constants import LANGUAGES, SUPPORTED_EXTENSIONS
from app.config import AppConfig, ConfigStore
from app.core.file_handler import FileHandler, UnsupportedFileTypeError
from app.core.pipeline import PipelineCancelled, ProcessingPipeline
from app.i18n import I18n
from app.models import ContentMode, ExportFormat, ProcessMode, ProcessingTask


class PipelineWorker(QObject):
    progress = Signal(int, str)
    log = Signal(str)
    succeeded = Signal(list)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, config: AppConfig, task: ProcessingTask) -> None:
        super().__init__()
        self.pipeline = ProcessingPipeline(
            config,
            progress_callback=self.progress.emit,
            log_callback=self.log.emit,
        )
        self.task = task

    def run(self) -> None:
        try:
            outputs = self.pipeline.run(self.task)
        except PipelineCancelled:
            self.failed.emit("任务已取消")
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(outputs)
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        self.pipeline.cancel()


class HomeInterface(QWidget):
    def __init__(self, config: AppConfig, parent: QWidget | None = None, *, store: ConfigStore | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("homeInterface")
        self.setAcceptDrops(True)
        self.config = config
        self.store = store
        self.i18n = I18n(config.language)
        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.viewport().setAutoFillBackground(False)
        content = QWidget()
        self.scroll_area.setWidget(content)
        content.setAutoFillBackground(False)
        page_layout.addWidget(self.scroll_area)
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        root.addWidget(SubtitleLabel(self.i18n("home")))

        file_card = CardWidget(content)
        file_layout = QVBoxLayout(file_card)
        buttons = QHBoxLayout()
        self.add_button = PrimaryPushButton(self.i18n("add_files"))
        self.remove_button = PushButton(self.i18n("remove_selected"))
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        file_layout.addLayout(buttons)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["文件名", "类型", "大小"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        file_layout.addWidget(self.table)
        root.addWidget(file_card, 3)

        options_card = CardWidget(content)
        form = QFormLayout(options_card)
        self.source_language = QComboBox()
        self.source_language.addItems(["自动检测", *LANGUAGES])
        selected = next((label for label in ["自动检测", *LANGUAGES]
                         if ProcessingPipeline._asr_language(label) == self.config.asr_language
                         or label == self.config.asr_language), "自动检测")
        self.source_language.setCurrentText(selected)
        self.source_language.setToolTip("自动检测由 Whisper 模型完成；已知源语言时可直接指定")
        self.source_language.currentTextChanged.connect(self._save_source_language)
        self.target_language = QComboBox()
        self.target_language.addItems(LANGUAGES)
        self.export_format = QComboBox()
        self.export_format.addItems(["SRT (.srt)", "LRC (.lrc)"])
        self.content_mode = QComboBox()
        self.content_mode.addItems([self.i18n("bilingual"), self.i18n("source_only"), self.i18n("target_only")])
        self.process_mode = SegmentedWidget()
        self.process_mode.addItem("transcribe", self.i18n("transcribe_only"))
        self.process_mode.addItem("translate", self.i18n("transcribe_translate"))
        self.process_mode.setCurrentItem("translate")
        form.addRow(self.i18n("source_language"), self.source_language)
        form.addRow(self.i18n("target_language"), self.target_language)
        form.addRow(self.i18n("export_format"), self.export_format)
        form.addRow(self.i18n("content_mode"), self.content_mode)
        form.addRow(self.i18n("process_mode"), self.process_mode)
        root.addWidget(options_card)

        control = QHBoxLayout()
        self.start_button = PrimaryPushButton(self.i18n("start"))
        self.cancel_button = PushButton(self.i18n("cancel"))
        self.cancel_button.setEnabled(False)
        self.progress = ProgressBar()
        self.progress.setValue(0)
        control.addWidget(self.start_button)
        control.addWidget(self.cancel_button)
        control.addWidget(self.progress, 1)
        root.addLayout(control)
        self.log_output = TextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("处理日志")
        root.addWidget(self.log_output, 2)

        self.add_button.clicked.connect(self._choose_files)
        self.remove_button.clicked.connect(self._remove_selected)
        self.start_button.clicked.connect(self._start)
        self.cancel_button.clicked.connect(self._cancel)
        self.process_mode.currentItemChanged.connect(self._sync_mode)

    def _save_source_language(self, value: str) -> None:
        self.config.asr_language = ProcessingPipeline._asr_language(value)
        if self.store is not None:
            self.store.save(self.config)

    def _choose_files(self) -> None:
        patterns = " ".join(f"*{suffix}" for suffix in sorted(SUPPORTED_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(self, "选择音视频、字幕或歌词", "", f"支持的文件 ({patterns});;所有文件 (*)")
        self.add_files(files)

    def add_files(self, paths: list[str]) -> None:
        existing = {self.table.item(row, 0).data(256) for row in range(self.table.rowCount())}
        handler = FileHandler(self.config.ffmpeg_path)
        for raw in paths:
            path = Path(raw)
            if str(path) in existing or not path.is_file():
                continue
            try:
                kind = handler.detect_type(path)
            except UnsupportedFileTypeError as exc:
                InfoBar.warning("不支持的文件", str(exc), parent=self, position=InfoBarPosition.TOP)
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = QTableWidgetItem(path.name)
            name.setData(256, str(path))
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(kind.value))
            self.table.setItem(row, 2, QTableWidgetItem(self._size(path.stat().st_size)))
            existing.add(str(path))

    def _remove_selected(self) -> None:
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def _sync_mode(self, key: str) -> None:
        translating = key == "translate"
        self.target_language.setEnabled(translating)
        self.content_mode.setEnabled(translating)
        if not translating:
            if any(self.table.item(row, 1).text() in {"subtitle", "lyrics"} for row in range(self.table.rowCount())):
                InfoBar.info("提示", "字幕或歌词已包含文本，无需转录；将直接导出。", parent=self, position=InfoBarPosition.TOP)

    def _start(self) -> None:
        files = [self.table.item(row, 0).data(256) for row in range(self.table.rowCount())]
        if not files:
            InfoBar.warning("无法开始", "请先添加文件", parent=self, position=InfoBarPosition.TOP)
            return
        mode = self._process_mode_from_key(self.process_mode.currentRouteKey())
        content_modes = [ContentMode.BILINGUAL, ContentMode.SOURCE_ONLY, ContentMode.TARGET_ONLY]
        task = ProcessingTask(
            input_files=files,
            source_language=self.source_language.currentText(),
            target_language=self.target_language.currentText(),
            export_format=ExportFormat.SRT if self.export_format.currentIndex() == 0 else ExportFormat.LRC,
            content_mode=content_modes[self.content_mode.currentIndex()],
            process_mode=mode,
            output_directory=(
                self.config.output_directory if self.config.output_directory_mode == "custom" else ""
            ),
        )
        self.log_output.clear()
        self.progress.setValue(0)
        self._thread = QThread(self)
        self._worker = PipelineWorker(self.config, task)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self.log_output.append)
        self._worker.succeeded.connect(self._succeeded)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._finish)
        self._thread.finished.connect(self._thread.deleteLater)
        self.start_button.setEnabled(False)
        self.source_language.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self._thread.start()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.cancel_button.setEnabled(False)

    def _on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.log_output.append(message)

    def _succeeded(self, outputs: list[str]) -> None:
        InfoBar.success("处理完成", f"已生成 {len(outputs)} 个文件", parent=self, position=InfoBarPosition.TOP)

    def _failed(self, message: str) -> None:
        InfoBar.error("处理未完成", message, parent=self, position=InfoBarPosition.TOP, duration=6000)

    def _finish(self) -> None:
        self.source_language.setEnabled(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._worker = None

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])

    @staticmethod
    def _size(value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    @staticmethod
    def _process_mode_from_key(key: str | None) -> ProcessMode:
        if key == "translate":
            return ProcessMode.TRANSCRIBE_AND_TRANSLATE
        return ProcessMode.TRANSCRIBE_ONLY
