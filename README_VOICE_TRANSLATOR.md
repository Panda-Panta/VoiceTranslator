# VoiceTranslator

支持在“全局设置 → 外观”中选择自定义背景图，并调整填充、适应、拉伸或平铺方式以及背景图不透明度。

面向 Windows 的本地化优先音视频转录翻译桌面应用。项目采用独立的 PySide6 分层架构，新入口为 main.py；旧 GalTransl 后端、插件系统和 PyQt5 界面不属于本项目运行代码。

## 当前架构

- 默认转录：CrispASR CUDA + Whisper large-v2-q8_0
- 可选转录：Qwen3-ASR 1.7B + Qwen3 Forced Aligner
- 时间轴：Whisper 原生时间戳，或 Qwen3 Forced Aligner + Silero VAD
- 强背景音乐：使用官方清单收录的 Kim Vocal 2 ONNX 直接提取人声
- 本地翻译：llama-server + Hy-MT2/Qwen/Gemma GGUF
- 在线翻译：OpenAI 兼容 API
- 输出：SRT/LRC，可选原文、译文或双语

当前版本可在 Whisper 与 Qwen3-ASR 之间切换。Qwen3-ASR 使用独立的 Qwen3 Forced Aligner 生成字幕时间轴。CrispASR 每次转录在独立子进程中运行；进程退出后才允许加载本地翻译模型，因此成功、异常、取消和关闭应用都会释放 ASR 内存与显存。

## 安装

需要 Windows、Python 3.10+ 和 FFmpeg。先安装 Python 依赖：

    python -m pip install -r requirements-voicetranslator.txt

一键安装 CUDA 版 CrispASR、Whisper large-v2 Q8 和 Silero VAD，并自动更新 %APPDATA%\VoiceTranslator\config.json：

    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools\setup_whisper_runtime.ps1

Whisper、Qwen3-ASR、Forced Aligner、Silero VAD、Kim Vocal 2 与 Hy-MT2 的下载链接、推荐规格和手动配置方法见 [MODEL_GUIDE.md](MODEL_GUIDE.md)。

可选模型和运行时：

    # 较低显存占用，约 1.08 GB
    tools\setup_whisper_runtime.ps1 -Model large-v2-q5_0

    # 非量化 large-v2，约 3.1 GB
    tools\setup_whisper_runtime.ps1 -Model large-v2

    # 完整架构 large-v3 Q5，作为可选对比模型
    tools\setup_whisper_runtime.ps1 -Model large-v3-q5_0

    # 更快、占用更低的 large-v3-turbo Q5
    tools\setup_whisper_runtime.ps1 -Model large-v3-turbo-q5_0

    # AMD/Intel/NVIDIA 通用 Vulkan
    tools\setup_whisper_runtime.ps1 -Runtime vulkan

检查完整运行时：

    python tools\check_whisper_runtime.py

启动应用：

    python main.py

## 设置

1. “全局设置”配置 CrispASR、llama-server、FFmpeg 和默认输出位置。
   外观中的“字体比例”可在 80%–200% 间调整，保存后立即生效。
2. “转录设置”可选择 Whisper 或 Qwen3-ASR 后端。Whisper 选择 `.bin`；Qwen3-ASR 选择主模型 `.gguf` 和 Forced Aligner `.gguf`。
3. GPU 加速设为非 0 时使用 GPU；设为 0 强制 CPU。多 GPU 可设置设备编号。
4. 处理明显伴奏时，可选择 `Kim_Vocal_2.onnx` 并启用自动人声分离；模型输出会直接作为所选 ASR 后端的人声输入。
5. “翻译设置”选择本地 GGUF，或配置在线 API。

默认输出目录为源文件所在目录。“仅转录”不会修改已保存的导出设置。

## 处理顺序

1. 解析字幕或准备音视频。
2. 可选人声分离；完成后卸载分离模型。
3. Whisper 或 Qwen3-ASR + Silero VAD 转录；Qwen3-ASR 通过 Forced Aligner 生成时间轴。
4. CrispASR 子进程退出，卸载 ASR 主模型和对齐模型。
5. 如需翻译，再加载本地翻译模型。
6. 翻译完成后停止 llama-server 并导出；每一条可见字幕行末的逗号、句号等分句标点会自动移除，句中标点保留。

VAD 负责检测语音区间，不负责消除与对白重叠的音乐；默认以 500 ms 静音分段并保留 150 ms 语音边缘。Qwen3 Forced Aligner 对开头静音较敏感，因此使用 Qwen3-ASR 时应保持 VAD 开启。转录后还会合并相邻短句、在标点附近拆分超长句并修正轻微时间轴重叠。强 BGM 使用 Kim Vocal 2 直接提取人声。ONNX 分离器在独立进程中运行，全部文件处理完即退出并释放模型，然后才加载 ASR。

## 验证

    python -m pytest -q

测试覆盖文件类型、SRT/LRC、Whisper 与 Qwen3-ASR 命令构造、Forced Aligner、VAD、Kim Vocal 2 直接人声提取、字幕重排、严格模型生命周期、翻译顺序和异常清理。项目还用真实日语音频验证了 Qwen3-ASR Q4/Q8、Forced Aligner、CUDA 转录、SRT 导出和进程卸载。

## 许可证

本项目以 GNU GPLv3-or-later 发布；详见 LICENSE。项目沿革、继承内容与第三方组件说明见 NOTICE.md。
