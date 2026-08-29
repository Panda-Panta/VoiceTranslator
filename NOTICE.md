# 来源与第三方组件说明

VoiceTranslator 是一个独立维护的软件项目，使用全新的 PySide6 分层架构实现本地音视频转录、字幕整理和翻译流程。

## 项目沿革

本项目最初参考了 [VoiceTransl](https://github.com/shinnpuru/VoiceTransl) 的产品定位和处理流程。VoiceTransl 本身基于 GalTransl，并采用 GNU GPLv3。VoiceTranslator 不包含原项目的 GalTransl 后端、插件系统、旧 PyQt5 界面、视频下载和字幕总结实现。

Qwen3-ASR 与 Qwen3 Forced Aligner 的兼容设计参考了 VoiceTransl 2026 年 8 月的 CrispASR 工作流；本项目在现有独立分层架构中重新实现了后端选择、配置迁移、短生命周期子进程和设置界面。

仓库中的 `separate.py` 继承并修改了上游的 MDX ONNX 人声分离实现；部分运行时说明文件也来自上游。上述内容与本项目其余代码统一依照 GNU GPLv3-or-later 发布。当前 `icon.png`、`icon.ico` 和 `icon.icns` 是 VoiceTranslator 的项目专用图标资源。

## 主要第三方组件

- PySide6 与 PySide6-Fluent-Widgets：桌面界面
- CrispASR、Whisper、Qwen3-ASR 与 Qwen3 Forced Aligner：本地语音识别和时间轴对齐
- FFmpeg：音视频解封装和音频提取
- ONNX Runtime 与 MDX 模型：人声提取
- llama.cpp：本地翻译模型服务

各组件和模型分别适用其原作者发布的许可证及使用条款。本仓库不宣称拥有这些第三方项目或模型。
