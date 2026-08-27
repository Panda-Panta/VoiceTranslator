# 模型下载与使用指南

GitHub 标准 Release 包含 VoiceTranslator 程序及对应平台的 CrispASR、llama-server 运行时，但不重复打包体积较大的 Whisper、翻译和人声分离模型。模型可放在任意目录；为了方便迁移，建议采用下面的目录结构：

```text
VoiceTranslator/
├─ models/
│  ├─ whisper/
│  ├─ separation/
│  └─ translation/
└─ runtime/
```

## 一键安装 Whisper 与 VAD

从源码目录运行以下命令，会下载 CrispASR、推荐的 Whisper large-v2 Q8 和 Silero VAD，并自动写入 `%APPDATA%\VoiceTranslator\config.json`：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File tools\setup_whisper_runtime.ps1 -Runtime cuda -Model large-v2-q8_0
```

AMD、Intel 或不想依赖 CUDA 的用户可将 `-Runtime cuda` 改为 `-Runtime vulkan`。CPU 模式使用 `-Runtime cpu`。

## Whisper 转录模型

模型来源：[ggerganov/whisper.cpp 模型仓库](https://huggingface.co/ggerganov/whisper.cpp/tree/main)。

| 模型 | 大小 | 建议用途 | 下载 |
|---|---:|---|---|
| large-v2 Q8 | 1.66 GB | 默认推荐；日语动画、对白和背景音乐场景优先 | [ggml-large-v2-q8_0.bin](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v2-q8_0.bin) |
| large-v2 Q5 | 1.08 GB | 显存或内存较紧张 | [ggml-large-v2-q5_0.bin](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v2-q5_0.bin) |
| large-v2 F16 | 3.09 GB | 最大限度保留模型精度，资源占用最高 | [ggml-large-v2.bin](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v2.bin) |
| large-v3 Q5 | 1.08 GB | 与 V2 对比，适合部分多语言材料 | [ggml-large-v3-q5_0.bin](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-q5_0.bin) |
| large-v3-turbo Q5 | 574 MB | 更重视速度和较低占用 | [ggml-large-v3-turbo-q5_0.bin](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin) |

手动下载后，在“转录设置 → Whisper 模型路径”中选择 `.bin` 文件。模型规格会从文件名自动识别，不需要再单独选择。

## Silero VAD

下载 [ggml-silero-v6.2.0.bin](https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin)，然后在“转录设置 → VAD 模型路径”中选择该文件，并启用 VAD。

VAD 只负责检测有语音的时间区间，不能去除和对白同时出现的音乐。默认设置建议保持：最小静音 `500 ms`、语音边缘填充 `150 ms`。

## Kim Vocal 2 人声提取模型

下载 UVR 公共模型仓库中的 [Kim_Vocal_2.onnx](https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/Kim_Vocal_2.onnx)，建议保存为：

```text
models\separation\Kim_Vocal_2.onnx
```

然后打开“转录设置”：

1. 勾选“自动人声分离”。
2. 在“直接人声提取 ONNX 模型”中选择 `Kim_Vocal_2.onnx`。
3. 正常开始转录。软件会把模型的人声输出送入 Whisper，而不是把伴奏输出送入识别器。
4. 全部音频分离完成后，ONNX 子进程会退出并释放模型，再加载 Whisper。

## Hy-MT2 本地翻译模型

推荐使用腾讯官方 [Hy-MT2-1.8B-GGUF](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/tree/main)：

| 量化 | 大小 | 建议用途 | 下载 |
|---|---:|---|---|
| Q8_0 | 1.91 GB | 默认推荐，翻译质量优先 | [Hy-MT2-1.8B-Q8_0.gguf](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q8_0.gguf) |
| Q6_K | 1.47 GB | 质量与体积折中 | [Hy-MT2-1.8B-Q6_K.gguf](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q6_K.gguf) |
| Q4_K_M | 1.13 GB | 内存或显存较小 | [Hy-MT2-1.8B-Q4_K_M.gguf](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q4_K_M.gguf) |

建议保存到 `models\translation\`。在 VoiceTranslator 中：

1. “全局设置 → llama-server 路径”选择 Release 包内或自行下载的 `llama-server.exe`。
2. “翻译设置 → 翻译引擎”选择“本地模型”。
3. “本地翻译模型”选择下载的 `.gguf` 文件。
4. 6 GB 显存可优先尝试 Q8_0；显存不足时改用 Q6_K 或 Q4_K_M，或者降低 GPU 层数。
5. 选择“转录并翻译”或输入现有 SRT 后执行翻译。翻译结束后 llama-server 会自动停止并释放模型。

## 最小推荐组合

- Whisper：`ggml-large-v2-q8_0.bin`
- VAD：`ggml-silero-v6.2.0.bin`
- 强背景音乐：`Kim_Vocal_2.onnx`
- 本地翻译：`Hy-MT2-1.8B-Q8_0.gguf`

如果只进行转录，不需要下载 Hy-MT2；如果音频没有明显音乐，也可以关闭人声分离。
