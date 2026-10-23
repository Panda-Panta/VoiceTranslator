# VoiceTranslator

支持在“全局设置 → 外观”中选择自定义背景图，并调整填充、适应、拉伸或平铺方式以及背景图不透明度。

面向 Windows 的本地化优先音视频转录翻译桌面应用。项目采用独立的 PySide6 分层架构，新入口为 main.py；旧 GalTransl 后端、插件系统和 PyQt5 界面不属于本项目运行代码。

## 当前架构

- 默认转录：CrispASR CUDA + Whisper large-v2-q8_0
- 时间轴：Whisper 原生时间戳 + Silero VAD
- 强背景音乐：使用官方清单收录的 Kim Vocal 2 ONNX 直接提取人声
- 本地翻译：llama-server + Hy-MT2/Qwen/Gemma GGUF
- 在线翻译：OpenAI 兼容 API
- 输出：SRT/LRC，可选原文、译文或双语

当前源码只使用 Whisper 转录，语言检测直接由所选 Whisper 模型完成。CrispASR 每次转录在独立子进程中运行；进程退出后才允许加载本地翻译模型，因此成功、异常、取消和关闭应用都会释放 ASR 内存与显存。

未发布更新：已移除 Qwen ASR 支持。旧配置会保留独立的 Whisper 设置和其他偏好，清除 Qwen ASR、对齐模型及附加语言检测模型设置。之前仅配置 Qwen ASR 的用户需要选择 Whisper `.bin` 模型；程序会优先发现本地已安装的 Whisper。已下载的模型文件不会被删除，Qwen 文本翻译模型仍可使用。

## 安装

需要 Windows、Python 3.10+ 和 FFmpeg。先安装 Python 依赖：

    python -m pip install -r requirements-voicetranslator.txt

一键安装 CUDA 版 CrispASR、Whisper large-v2 Q8 和 Silero VAD，并自动更新 %APPDATA%\VoiceTranslator\config.json：

    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools\setup_whisper_runtime.ps1

Whisper、Silero VAD、Kim Vocal 2 与 Hy-MT2 的下载链接、推荐规格和手动配置方法见 [MODEL_GUIDE.md](MODEL_GUIDE.md)。

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
2. “转录设置”选择 Whisper `.bin` 模型和 Silero VAD 模型；首页“源语言”可自动检测或指定语言，与“目标语言”独立。
3. GPU 加速设为非 0 时使用 GPU；设为 0 强制 CPU。多 GPU 可设置设备编号。
4. 处理明显伴奏时，可选择 `Kim_Vocal_2.onnx` 并启用自动人声分离；模型输出会直接作为 Whisper 的人声输入。
5. “翻译设置”选择本地 GGUF，或配置在线 API。

默认输出目录为源文件所在目录。“仅转录”不会修改已保存的导出设置。

## 处理顺序

1. 解析字幕或准备音视频。
2. 可选人声分离；完成后卸载分离模型。
3. Whisper + Silero VAD 转录，使用 Whisper 原生时间戳。
4. CrispASR 子进程退出，卸载 ASR 模型。
5. 如需翻译，再加载本地翻译模型。
6. 翻译完成后停止 llama-server 并导出；每一条可见字幕行末的逗号、句号等分句标点会自动移除，句中标点保留。

VAD 负责检测语音区间，不负责消除与对白重叠的音乐；默认以 500 ms 静音分段并保留 150 ms 语音边缘。转录后还会合并相邻短句、在标点附近拆分超长句并修正轻微时间轴重叠。强 BGM 使用 Kim Vocal 2 直接提取人声。ONNX 分离器在独立进程中运行，全部文件处理完即退出并释放模型，然后才加载 ASR。

## 验证

    python -m pytest -q

测试覆盖文件类型、SRT/LRC、Whisper 命令构造、自动/指定源语言、旧配置迁移、设置保存、VAD、Kim Vocal 2 直接人声提取、字幕重排、严格模型生命周期、翻译顺序和异常清理。模型推理实测需要额外安装 CrispASR 和 Whisper；本次更新的验证结果与范围见 [实施计划](implementation_plan_v2.md)。

## 维护入口

- `app/config.py`：配置读写、旧配置迁移和运行时发现。
- `app/core/`：Whisper 子进程、音视频处理、字幕和翻译管线。
- `app/views/`：首页、主窗口和集中维护的 `settings_interfaces.py` 设置页。
- `tests/`：pytest 自动回归；`tools/`：环境安装、检查与便携包构建工具。
- `runtime/`：本机运行时和模型；`build/`：构建及验证中间产物；`release/`：已有发布产物。这些目录不纳入源码提交，用户模型及旧版本不得按本次代码移除一并删除。
- 当前完整计划与开发记录统一维护在 [implementation_plan_v2.md](implementation_plan_v2.md)。

## 许可证

本项目以 GNU GPLv3-or-later 发布；详见 LICENSE。项目沿革、继承内容与第三方组件说明见 NOTICE.md。
