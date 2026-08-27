# VoiceTranslator

面向 Windows 的本地化优先音视频转录、字幕整理与翻译桌面应用。项目采用独立的 PySide6 分层架构，以 Whisper 为转录核心，并支持人声提取和本地大模型翻译。

## 核心功能

- Whisper large-v2 为默认转录模型，可选 large-v3
- Silero VAD 与字幕重排
- Kim Vocal 2 ONNX 直接提取人声
- llama.cpp 本地翻译或 OpenAI 兼容在线 API
- SRT/LRC 原文、译文与双语输出
- 各阶段结束后自动卸载模型
- 80%–200% 全局字体比例

## 安装与启动

    python -m pip install -r requirements-voicetranslator.txt
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools\setup_whisper_runtime.ps1
    python main.py

完整架构、模型与设置说明见 [README_VOICE_TRANSLATOR.md](README_VOICE_TRANSLATOR.md)。

模型不会随标准 Release 重复打包。下载地址、推荐规格、目录结构和界面配置步骤见 [模型下载与使用指南](MODEL_GUIDE.md)。

## 许可证

本项目以 GNU GPLv3-or-later 发布，详见 [LICENSE](LICENSE)。项目最初参考 [VoiceTransl](https://github.com/shinnpuru/VoiceTransl) 的产品流程重新设计；继承内容和第三方组件说明见 [NOTICE.md](NOTICE.md)。
