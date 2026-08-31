from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CardWidget, InfoBar, InfoBarPosition, PrimaryPushButton, SubtitleLabel

from app.common.constants import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_TRANSLATION_PROMPT,
    PROJECT_REPOSITORY_URL,
    UPSTREAM_REPOSITORY_URL,
)
from app.config import AppConfig, ConfigStore
from app.core.translator import OnlineTranslator
from app.ui_scale import apply_font_scale


class PathPicker(QWidget):
    def __init__(self, value: str = "", directory: bool = False, file_filter: str = "所有文件 (*)") -> None:
        super().__init__()
        self.directory = directory
        self.file_filter = file_filter
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(value)
        button = QPushButton("浏览…")
        button.clicked.connect(self._browse)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def _browse(self) -> None:
        if self.directory:
            value = QFileDialog.getExistingDirectory(self, "选择目录", self.edit.text())
        else:
            value, _ = QFileDialog.getOpenFileName(self, "选择文件", self.edit.text(), self.file_filter)
        if value:
            self.edit.setText(value)

    def text(self) -> str:
        return self.edit.text().strip()


class SettingsPage(QScrollArea):
    def __init__(self, title: str, config: AppConfig, store: ConfigStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.store = store
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.viewport().setAutoFillBackground(False)
        content = QWidget()
        self.root = QVBoxLayout(content)
        self.root.setContentsMargins(28, 24, 28, 24)
        self.root.setSpacing(16)
        self.root.addWidget(SubtitleLabel(title))
        self.setWidget(content)
        content.setAutoFillBackground(False)

    def add_group(self, title: str) -> QFormLayout:
        card = CardWidget()
        layout = QVBoxLayout(card)
        heading = QLabel(title)
        heading.setStyleSheet("font-weight: 600")
        layout.addWidget(heading)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        self.root.addWidget(card)
        return form

    def finish(self, callback: Callable[[], None]) -> None:
        button = PrimaryPushButton("保存设置")
        button.clicked.connect(callback)
        self.root.addWidget(button, alignment=Qt.AlignLeft)
        self.root.addStretch(1)

    def saved(self) -> None:
        self.store.save(self.config)
        InfoBar.success("已保存", "设置已保存", parent=self, position=InfoBarPosition.TOP)


class GeneralSettingsInterface(SettingsPage):
    appearanceChanged = Signal()

    def __init__(self, config: AppConfig, store: ConfigStore) -> None:
        super().__init__("全局设置", config, store)
        self.setObjectName("generalSettingsInterface")
        appearance = self.add_group("外观")
        self.theme = QComboBox()
        self.theme.addItems(["跟随系统", "浅色", "深色"])
        self.theme.setCurrentIndex({"system": 0, "light": 1, "dark": 2}.get(config.theme, 0))
        self.language = QComboBox()
        self.language.addItems(["简体中文", "English"])
        self.language.setCurrentIndex(1 if config.language == "en_US" else 0)
        self.theme_color = QPushButton(config.theme_color)
        self.theme_color.clicked.connect(self._choose_color)
        self.font_scale = QSpinBox()
        self.font_scale.setRange(80, 200)
        self.font_scale.setSingleStep(5)
        self.font_scale.setSuffix("%")
        self.font_scale.setValue(config.ui_font_scale)
        self.background_enabled = QCheckBox("启用自定义背景图")
        self.background_enabled.setChecked(config.background_enabled)
        self.background_image = PathPicker(
            config.background_image_path,
            file_filter="图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)",
        )
        self.background_scale = QComboBox()
        self.background_scale.addItem("填充窗口（保持比例并裁剪）", "cover")
        self.background_scale.addItem("适应窗口（完整显示）", "contain")
        self.background_scale.addItem("拉伸到窗口", "stretch")
        self.background_scale.addItem("平铺", "tile")
        background_scale_index = self.background_scale.findData(config.background_scale_mode)
        self.background_scale.setCurrentIndex(max(0, background_scale_index))
        self.background_opacity = QSpinBox()
        self.background_opacity.setRange(0, 100)
        self.background_opacity.setSuffix("%")
        self.background_opacity.setValue(config.background_opacity)
        self.background_opacity.setToolTip("0% 为完全透明，100% 为完全不透明")
        self.background_enabled.toggled.connect(self._sync_background)
        appearance.addRow("主题模式", self.theme)
        appearance.addRow("主题色", self.theme_color)
        appearance.addRow("字体比例", self.font_scale)
        appearance.addRow("界面语言（重启后生效）", self.language)
        appearance.addRow(self.background_enabled)
        appearance.addRow("背景图片", self.background_image)
        appearance.addRow("缩放方式", self.background_scale)
        appearance.addRow("背景图不透明度", self.background_opacity)
        self._sync_background()
        paths = self.add_group("路径")
        self.server = PathPicker(config.llama_server_path, file_filter="llama-server (llama-server.exe);;所有文件 (*)")
        self.crispasr = PathPicker(config.crispasr_path, file_filter="CrispASR (crispasr.exe);;所有文件 (*)")
        self.ffmpeg = PathPicker(config.ffmpeg_path, file_filter="可执行文件 (*.exe);;所有文件 (*)")
        self.output_mode = QComboBox()
        self.output_mode.addItems(["与源文件相同目录", "自定义目录"])
        self.output_mode.setCurrentIndex(1 if config.output_directory_mode == "custom" else 0)
        self.output = PathPicker(config.output_directory, directory=True)
        self.output_mode.currentIndexChanged.connect(self._sync_output_mode)
        self._sync_output_mode()
        paths.addRow("llama-server 路径", self.server)
        paths.addRow("CrispASR 路径", self.crispasr)
        paths.addRow("FFmpeg 路径", self.ffmpeg)
        paths.addRow("默认输出位置", self.output_mode)
        paths.addRow("默认输出目录", self.output)
        behavior = self.add_group("行为")
        self.notify = QCheckBox("处理完成后通知")
        self.notify.setChecked(config.notify_when_done)
        self.open_output = QCheckBox("处理完成后自动打开输出目录")
        self.open_output.setChecked(config.open_output_directory)
        behavior.addRow(self.notify)
        behavior.addRow(self.open_output)
        self.finish(self._save)

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.theme_color.setText(color.name())

    def _sync_output_mode(self) -> None:
        self.output.setEnabled(self.output_mode.currentIndex() == 1)

    def _sync_background(self, _checked: bool = False) -> None:
        enabled = self.background_enabled.isChecked()
        self.background_image.setEnabled(enabled)
        self.background_scale.setEnabled(enabled)
        self.background_opacity.setEnabled(enabled)

    def _save(self) -> None:
        background_path = self.background_image.text()
        if self.background_enabled.isChecked() and not Path(background_path).expanduser().is_file():
            InfoBar.warning("背景图不可用", "请选择有效的背景图片文件", parent=self, position=InfoBarPosition.TOP)
            return
        self.config.theme = ["system", "light", "dark"][self.theme.currentIndex()]
        self.config.theme_color = self.theme_color.text()
        self.config.ui_font_scale = self.font_scale.value()
        self.config.background_enabled = self.background_enabled.isChecked()
        self.config.background_image_path = background_path
        self.config.background_scale_mode = str(self.background_scale.currentData())
        self.config.background_opacity = self.background_opacity.value()
        self.config.language = "en_US" if self.language.currentIndex() else "zh_CN"
        self.config.llama_server_path = self.server.text() or "llama-server"
        self.config.crispasr_path = self.crispasr.text() or "crispasr"
        self.config.ffmpeg_path = self.ffmpeg.text() or "ffmpeg"
        self.config.output_directory_mode = "custom" if self.output_mode.currentIndex() == 1 else "source"
        self.config.output_directory = self.output.text() if self.config.output_directory_mode == "custom" else ""
        self.config.notify_when_done = self.notify.isChecked()
        self.config.open_output_directory = self.open_output.isChecked()
        self.saved()
        apply_font_scale(self.config.ui_font_scale)
        self.appearanceChanged.emit()


class ASRSettingsInterface(SettingsPage):
    def __init__(self, config: AppConfig, store: ConfigStore) -> None:
        super().__init__("转录设置", config, store)
        self.setObjectName("asrSettingsInterface")
        preprocessing = self.add_group("音频预处理")
        self.separation_enabled = QCheckBox("转录前自动分离人声与背景音")
        self.separation_enabled.setChecked(config.vocal_separation_enabled)
        self.separation_model = PathPicker(
            config.vocal_separation_model_path,
            file_filter="UVR/MDX ONNX 模型 (*.onnx);;所有文件 (*)",
        )
        self.separation_enabled.toggled.connect(self._sync_separation)
        preprocessing.addRow(self.separation_enabled)
        preprocessing.addRow("直接人声提取 ONNX 模型", self.separation_model)
        self._sync_separation(self.separation_enabled.isChecked())
        model = self.add_group("语音识别模型")
        self.backend = QComboBox()
        self.backend.addItem("Whisper", "whisper")
        self.backend.addItem("Qwen3-ASR 1.7B + Forced Aligner", "qwen3-1.7b")
        backend_index = self.backend.findData(config.asr_backend)
        self.backend.setCurrentIndex(max(0, backend_index))

        self.whisper_model = PathPicker(
            config.asr_whisper_model_path,
            file_filter="Whisper 模型 (*.bin);;所有文件 (*)",
        )
        self.whisper_model.edit.setPlaceholderText("选择 ggml-large-v2-*.bin")
        self.whisper_model_detected = QLabel()
        self.whisper_model.edit.textChanged.connect(
            lambda value: self._sync_model_label(self.whisper_model_detected, value)
        )
        self._sync_model_label(self.whisper_model_detected, config.asr_whisper_model_path)
        whisper_panel = QWidget()
        whisper_form = QFormLayout(whisper_panel)
        whisper_form.setContentsMargins(0, 0, 0, 0)
        whisper_form.addRow("Whisper 模型", self.whisper_model)
        whisper_form.addRow("自动识别规格", self.whisper_model_detected)

        self.qwen_model = PathPicker(
            config.asr_qwen3_model_path,
            file_filter="Qwen3-ASR 模型 (*.gguf);;所有文件 (*)",
        )
        self.qwen_model.edit.setPlaceholderText("选择 qwen3-asr-1.7b-*.gguf")
        self.aligner_model = PathPicker(
            config.asr_qwen3_aligner_model_path,
            file_filter="Qwen3 Forced Aligner (*.gguf);;所有文件 (*)",
        )
        self.aligner_model.edit.setPlaceholderText("选择 qwen3-forced-aligner-0.6b-*.gguf")
        self.lid_model = PathPicker(config.asr_qwen3_lid_model_path, file_filter="多语言 Whisper 模型 (*.bin);;所有文件 (*)")
        self.lid_model.edit.setPlaceholderText("ggml-tiny.bin（仅自动检测源语言时需要）")
        self.qwen_model_detected = QLabel()
        self.qwen_model.edit.textChanged.connect(
            lambda value: self._sync_model_label(self.qwen_model_detected, value)
        )
        self._sync_model_label(self.qwen_model_detected, config.asr_qwen3_model_path)
        qwen_panel = QWidget()
        qwen_form = QFormLayout(qwen_panel)
        qwen_form.setContentsMargins(0, 0, 0, 0)
        qwen_form.addRow("Qwen3-ASR 主模型", self.qwen_model)
        qwen_form.addRow("Forced Aligner 对齐模型", self.aligner_model)
        qwen_form.addRow("语言检测模型（自动检测时）", self.lid_model)
        lid_hint = QLabel("首页可指定源语言以跳过检测；自动检测仅使用本地模型，不会后台下载。")
        lid_hint.setWordWrap(True)
        qwen_form.addRow(lid_hint)
        qwen_form.addRow("自动识别规格", self.qwen_model_detected)

        self.model_stack = QStackedWidget()
        self.model_stack.addWidget(whisper_panel)
        self.model_stack.addWidget(qwen_panel)
        self.backend.currentIndexChanged.connect(self._sync_backend)
        model.addRow("转录后端", self.backend)
        model.addRow(self.model_stack)
        self._sync_backend()
        inference = self.add_group("通用推理参数")
        self.gpu = self._spin(0, 999, config.asr_gpu_layers)
        self.threads = self._spin(1, 32, config.asr_threads)
        self.device = self._spin(0, 31, config.asr_device)
        self.timestamps = QCheckBox("生成片段时间戳")
        self.timestamps.setChecked(True)
        self.timestamps.setEnabled(False)
        self.vad = QCheckBox("启用 Silero VAD（推荐）")
        self.vad.setChecked(config.asr_vad_enabled)
        self.vad_model = PathPicker(config.asr_vad_model_path, file_filter="Silero VAD 模型 (*.bin);;所有文件 (*)")
        self.vad_silence = self._spin(0, 5000, config.asr_vad_min_silence_ms)
        self.vad_speech_pad = self._spin(0, 2000, config.asr_vad_speech_pad_ms)
        self.split_punctuation = QCheckBox("按标点强制拆分字幕")
        self.split_punctuation.setChecked(config.asr_split_on_punctuation)
        inference.addRow("GPU 加速（0 = CPU，非 0 = GPU）", self.gpu)
        inference.addRow("GPU 设备编号", self.device)
        inference.addRow("线程数", self.threads)
        inference.addRow(self.timestamps)
        inference.addRow(self.vad)
        inference.addRow("Silero VAD 模型", self.vad_model)
        inference.addRow("VAD 分段静音（毫秒）", self.vad_silence)
        inference.addRow("VAD 语音边缘保护（毫秒）", self.vad_speech_pad)
        inference.addRow(self.split_punctuation)
        segmentation = self.add_group("字幕重排")
        self.resegment = QCheckBox("转录后自动优化断句与时间轴")
        self.resegment.setChecked(config.subtitle_resegment_enabled)
        self.subtitle_max_chars = self._spin(8, 100, config.subtitle_max_chars)
        self.subtitle_max_duration = QDoubleSpinBox()
        self.subtitle_max_duration.setRange(1.0, 20.0)
        self.subtitle_max_duration.setSingleStep(0.5)
        self.subtitle_max_duration.setValue(config.subtitle_max_duration)
        self.subtitle_merge_gap = self._spin(0, 2000, config.subtitle_merge_gap_ms)
        segmentation.addRow(self.resegment)
        segmentation.addRow("每条最大字符数", self.subtitle_max_chars)
        segmentation.addRow("每条最长时间（秒）", self.subtitle_max_duration)
        segmentation.addRow("合并短句间隔（毫秒）", self.subtitle_merge_gap)
        advanced = self.add_group("后端高级参数")
        self.whisper_extra = QLineEdit(config.asr_whisper_extra_args)
        self.qwen_extra = QLineEdit(config.asr_qwen3_extra_args)
        whisper_advanced = QWidget()
        whisper_advanced_form = QFormLayout(whisper_advanced)
        whisper_advanced_form.setContentsMargins(0, 0, 0, 0)
        whisper_advanced_form.addRow("Whisper 自定义启动参数", self.whisper_extra)
        qwen_advanced = QWidget()
        qwen_advanced_form = QFormLayout(qwen_advanced)
        qwen_advanced_form.setContentsMargins(0, 0, 0, 0)
        qwen_advanced_form.addRow("Qwen3-ASR 自定义启动参数", self.qwen_extra)
        self.extra_stack = QStackedWidget()
        self.extra_stack.addWidget(whisper_advanced)
        self.extra_stack.addWidget(qwen_advanced)
        advanced.addRow(self.extra_stack)
        self._sync_backend()
        self.finish(self._save)

    @staticmethod
    def _spin(minimum: int, maximum: int, value: int) -> QSpinBox:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        return widget

    def _save(self) -> None:
        self.config.vocal_separation_enabled = self.separation_enabled.isChecked()
        self.config.vocal_separation_model_path = self.separation_model.text()
        self.config.asr_backend = str(self.backend.currentData())
        self.config.asr_whisper_model_path = self.whisper_model.text()
        self.config.asr_qwen3_model_path = self.qwen_model.text()
        self.config.asr_qwen3_aligner_model_path = self.aligner_model.text()
        self.config.asr_qwen3_lid_model_path = self.lid_model.text()
        self.config.asr_gpu_layers = self.gpu.value()
        self.config.asr_threads = self.threads.value()
        self.config.asr_device = self.device.value()
        self.config.asr_timestamps = True
        self.config.asr_vad_enabled = self.vad.isChecked()
        self.config.asr_vad_model_path = self.vad_model.text()
        self.config.asr_vad_min_silence_ms = self.vad_silence.value()
        self.config.asr_vad_speech_pad_ms = self.vad_speech_pad.value()
        self.config.asr_split_on_punctuation = self.split_punctuation.isChecked()
        self.config.subtitle_resegment_enabled = self.resegment.isChecked()
        self.config.subtitle_max_chars = self.subtitle_max_chars.value()
        self.config.subtitle_max_duration = self.subtitle_max_duration.value()
        self.config.subtitle_merge_gap_ms = self.subtitle_merge_gap.value()
        self.config.asr_whisper_extra_args = self.whisper_extra.text().strip()
        self.config.asr_qwen3_extra_args = self.qwen_extra.text().strip()
        self.saved()

    def _sync_separation(self, _value: int | bool = False) -> None:
        enabled = self.separation_enabled.isChecked()
        self.separation_model.setEnabled(enabled)

    @staticmethod
    def _sync_model_label(label: QLabel, value: str) -> None:
        name = Path(value.strip()).stem
        if name.lower().startswith("ggml-"):
            name = name[5:]
        label.setText(name or "未选择模型")

    def _sync_backend(self, _index: int = 0) -> None:
        is_qwen3 = self.backend.currentData() == "qwen3-1.7b"
        index = 1 if is_qwen3 else 0
        self.model_stack.setCurrentIndex(index)
        if hasattr(self, "extra_stack"):
            self.extra_stack.setCurrentIndex(index)


class TranslationSettingsInterface(SettingsPage):
    def __init__(self, config: AppConfig, store: ConfigStore) -> None:
        super().__init__("翻译设置", config, store)
        self.setObjectName("translationSettingsInterface")
        engine = self.add_group("引擎选择")
        self.engine = QComboBox()
        self.engine.addItems(["本地模型", "在线 API"])
        self.engine.setCurrentIndex(0 if config.translation_engine == "local" else 1)
        engine.addRow("翻译引擎", self.engine)
        local = self.add_group("本地模型")
        self.model = PathPicker(config.translation_model_path, file_filter="GGUF 模型 (*.gguf);;所有文件 (*)")
        self.gpu = ASRSettingsInterface._spin(0, 999, config.translation_gpu_layers)
        self.context = ASRSettingsInterface._spin(512, 131072, config.translation_context_size)
        self.context.setSingleStep(512)
        self.port = ASRSettingsInterface._spin(1024, 65535, config.translation_port)
        local.addRow("模型路径", self.model)
        local.addRow("GPU 层数", self.gpu)
        local.addRow("上下文长度", self.context)
        local.addRow("服务端口", self.port)
        online = self.add_group("在线 API")
        self.base_url = QLineEdit(config.api_base_url)
        self.api_key = QLineEdit(config.api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_model = QComboBox()
        self.api_model.setEditable(True)
        if config.api_model:
            self.api_model.addItem(config.api_model)
        refresh = QPushButton("刷新模型列表")
        refresh.clicked.connect(self._refresh_models)
        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.addWidget(self.api_model, 1)
        model_layout.addWidget(refresh)
        online.addRow("API Base URL", self.base_url)
        online.addRow("API Key", self.api_key)
        online.addRow("模型名称", model_row)
        parameters = self.add_group("翻译参数")
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 2)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(config.temperature)
        self.batch = ASRSettingsInterface._spin(1, 50, config.batch_size)
        self.prompt = QPlainTextEdit(config.translation_prompt or DEFAULT_TRANSLATION_PROMPT)
        self.prompt.setMinimumHeight(110)
        self.unload = QCheckBox("每个阶段完成后自动卸载模型（始终启用）")
        self.unload.setChecked(True)
        self.unload.setEnabled(False)
        parameters.addRow("Temperature", self.temperature)
        parameters.addRow("批量大小", self.batch)
        parameters.addRow("翻译提示词", self.prompt)
        parameters.addRow(self.unload)
        self.finish(self._save)

    def _refresh_models(self) -> None:
        try:
            models = OnlineTranslator.list_models(self.base_url.text().strip(), self.api_key.text())
        except Exception as exc:
            InfoBar.error("获取失败", str(exc), parent=self, position=InfoBarPosition.TOP)
            return
        current = self.api_model.currentText()
        self.api_model.clear()
        self.api_model.addItems(models)
        if current in models:
            self.api_model.setCurrentText(current)
        InfoBar.success("获取成功", f"找到 {len(models)} 个模型", parent=self, position=InfoBarPosition.TOP)

    def _save(self) -> None:
        self.config.translation_engine = "local" if self.engine.currentIndex() == 0 else "online"
        self.config.translation_model_path = self.model.text()
        self.config.translation_gpu_layers = self.gpu.value()
        self.config.translation_context_size = self.context.value()
        self.config.translation_port = self.port.value()
        self.config.api_base_url = self.base_url.text().strip()
        self.config.api_key = self.api_key.text()
        self.config.api_model = self.api_model.currentText().strip()
        self.config.temperature = self.temperature.value()
        self.config.batch_size = self.batch.value()
        self.config.translation_prompt = self.prompt.toPlainText().strip()
        self.config.auto_unload_models = True
        self.saved()


class AboutInterface(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("aboutInterface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 36)
        layout.addWidget(SubtitleLabel(f"{APP_NAME} {APP_VERSION}"))
        description = QLabel("本地化优先的 AI 音视频转录与翻译工具\nWhisper · Qwen3-ASR · CrispASR · llama.cpp · OpenAI 兼容 API")
        description.setWordWrap(True)
        layout.addWidget(description)
        license_label = QLabel("独立维护的本地转录与翻译软件，遵循 GNU GPLv3。\n关键依赖：PySide6、QFluentWidgets、CrispASR、FFmpeg、llama.cpp。")
        license_label.setWordWrap(True)
        layout.addWidget(license_label)
        repository = PrimaryPushButton("打开 VoiceTranslator 项目")
        repository.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(PROJECT_REPOSITORY_URL)))
        layout.addWidget(repository, alignment=Qt.AlignLeft)
        upstream = PrimaryPushButton("查看来源项目 VoiceTransl")
        upstream.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(UPSTREAM_REPOSITORY_URL)))
        layout.addWidget(upstream, alignment=Qt.AlignLeft)
        layout.addStretch(1)
