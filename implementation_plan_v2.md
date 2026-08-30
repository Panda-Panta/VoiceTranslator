# VoiceTranslator V2 — 重新设计实施计划书

## 1. 项目定位

VoiceTranslator V2 是一款 Windows 优先、本地化优先的音视频转录与字幕翻译工具，面向动画、影视、访谈、课程和带背景音乐的音频。

核心目标：

1. 默认使用 Whisper large-v3-turbo 生成高质量文本。
2. 使用 Silero VAD 与 Whisper 原生时间戳生成可靠的逐句时间轴。
3. 对带伴奏音频提供可选的 UVR/MDX 自动人声分离。
4. 支持本地 Hy-MT/Qwen/Gemma 等 GGUF 翻译模型及在线 OpenAI 兼容 API。
5. 严格串行执行重型模型，阶段完成后立即卸载，避免显存争抢。
6. 支持批量文件、SRT/LRC、双语字幕及源目录输出。

非目标：

- 不在首个稳定版本中实现视频下载、视频压制、字幕总结和说话人分离。
- 不同时驻留 ASR、分离和本地翻译模型。
- 不把在线服务作为默认路径。

---

## 2. 已确认结论与架构调整

| 项目 | 原始方案 | V2 决策 | 原因 |
|:---|:---|:---|:---|
| ASR 运行时 | llama-server | CrispASR CLI/进程管理 | 当前 llama.cpp 转录接口只返回普通 JSON，不能稳定提供片段级时间轴 |
| ASR 模型 | Qwen3-ASR 主 GGUF + mmproj | 当前仅 Whisper large-v3-turbo Q5 | Whisper 在 CrispASR 中直接提供成熟的原生时间戳；Qwen3 等以后完成兼容再加入 |
| 时间轴 | 假设 ASR API 返回 segments | Whisper 原生时间戳 + Silero VAD | 不需要额外加载 Forced Aligner，链路更简单、显存更低 |
| 背景音乐 | 直接送入 ASR | 可选 UVR/MDX ONNX 人声分离 | VAD 只能检测语音，不能去除与对白同时存在的音乐 |
| 本地翻译 | llama-server | 保留 llama-server | OpenAI 兼容聊天接口适合 Hy-MT2 等 GGUF 翻译模型 |
| 模型生命周期 | 任务后可能保持服务 | 每阶段完成立即终止进程 | 释放 RAM/显存，保证下一阶段有足够资源 |
| 批次顺序 | 可能边转录边翻译 | 全部转录完成后才允许翻译 | 保证完整上下文并避免 GPU 竞争 |
| 默认输出 | 自定义目录 | 默认与源文件相同，可改为自定义目录 | 符合桌面文件处理习惯 |

结论：V2 当前只以 CrispASR + Whisper 为正式 ASR；llama-server 只服务于本地文本翻译。

---

## 3. 总体处理管线

```mermaid
flowchart TD
    A[批量输入文件] --> B{文件类型}
    B -->|SRT/LRC| C[解析现有时间轴与文本]
    B -->|音频| D[准备音频]
    B -->|视频| E[FFmpeg 提取音频]
    E --> D

    D --> F{启用自动人声分离?}
    F -->|是| G[UVR/MDX ONNX 分离人声]
    G --> H[终止分离进程并卸载模型]
    H --> I[规范化为 16kHz 单声道 WAV]
    F -->|否| I

    I --> J[CrispASR: Silero VAD + Whisper]
    J --> L[读取 Whisper 原生时间戳并生成 segments]
    L --> M[全部文件转录完成]
    C --> M
    M --> N[终止 CrispASR 并释放 Whisper]

    N --> O{处理方式}
    O -->|仅转录| R[导出]
    O -->|转录+翻译| P[启动本地翻译服务或在线 API]
    P --> Q[按文件/批次翻译，使用完整上下文]
    Q --> S[终止本地翻译服务并卸载模型]
    S --> R
    R --> T[SRT/LRC 输出]
```

### 严格阶段顺序

1. 文件准备阶段。
2. 可选人声分离阶段。
3. 全批次转录与时间轴阶段。
4. ASR 完全卸载。
5. 全批次翻译阶段。
6. 翻译模型完全卸载。
7. 导出阶段。

任何阶段发生失败或取消时，都必须通过 `finally` 终止当前子进程并清理临时文件。

---

## 4. 音频预处理设计

### 4.1 普通音频

- 使用 FFmpeg 转换为 PCM 16-bit、16 kHz、单声道 WAV。
- 保留原始文件，不在源目录生成中间文件。
- 中间音频统一放入任务临时目录。

### 4.2 带背景音乐音频

自动人声分离为可选功能，默认关闭：

1. 视频先提取为 44.1 kHz 双声道 WAV，避免在分离前损失频谱信息。
2. 音频输入复制到临时目录。
3. 使用 UVR/MDX ONNX 模型分离人声与伴奏。
4. 根据模型类型选择输出：
   - 模型预测伴奏：使用残差人声轨。
   - 模型预测人声：直接使用模型输出轨。
5. 分离完成后终止独立进程，确保 ONNX 模型和 DirectML 显存释放。
6. 将人声轨规范化为 16 kHz 单声道 WAV，再交给 CrispASR。

必须在 UI 中明确显示“模型输出伴奏”或“模型输出人声”，不能仅依赖文件名判断。

### 4.3 VAD 的职责边界

VAD 只负责：

- 跳过无语音区间。
- 按停顿切分语音段。
- 降低长音频一次推理的长度。

VAD 不负责：

- 去除与对白同时出现的音乐。
- 去混响。
- 消除持续风声、电流声。

---

## 5. 转录与时间轴设计

### 5.1 CrispASR 命令

基准调用形式：

```text
crispasr.exe
  --backend whisper
  --model <ggml-large-v3-turbo-q5_0.bin>
  --language auto
  --output-srt
  --output-file <temp/output>
  --file <temp/input.wav>
  --vad
  --vad-model <ggml-silero-v6.2.0.bin>
  --vad-min-silence-duration-ms 200
  --split-on-punct
```

### 5.2 模型职责

- Whisper：识别语言和文字，并原生生成片段时间戳。
- Silero VAD：寻找语音区间并将时间映射回原始音轨。
- Qwen3-ASR：暂不提供选项，等待后续完成运行时和时间轴兼容验证。

### 5.3 长文件

- 默认依赖 CrispASR VAD 处理。
- 可选启用“大文件恢复分段”，例如每 20–30 分钟切分。
- 每个大分段独立生成 SRT。
- 合并时累加精确音频时长偏移并重新编号。
- 翻译必须等所有分段合并为完整原文后才开始。

### 5.4 批量模型复用

第一阶段以“每文件一个 CrispASR 子进程”为可靠实现，确保崩溃隔离和自动卸载。

性能优化阶段再验证以下方案：

- CrispASR server 模式是否能返回与 CLI 一致的 Whisper segment 时间戳。
- 单进程重复 `-f` 输入是否能稳定产生独立输出。

只有在时间轴结果与 CLI 一致时，才允许改为常驻整个转录阶段的服务模式。

---

## 6. 翻译设计

### 6.1 本地翻译

- llama-server 仅加载翻译 GGUF。
- 默认端口 8080。
- 支持 Hy-MT2、Qwen、Gemma 等模型。
- Hy-MT2 使用官方“只输出译文”提示格式，不使用通用 JSON system prompt。
- 多条字幕通过不可翻译分隔符批处理；分隔符丢失时退化为逐条重试。

### 6.2 在线翻译

- 支持 OpenAI、DeepSeek 和任意 OpenAI 兼容端点。
- 支持 `GET /v1/models` 刷新模型列表。
- API Key 仅写入用户配置目录，不写入项目。

### 6.3 上下文策略

- 转录全部完成后构建完整上下文。
- 实际翻译按 1–50 条字幕分批。
- 每批携带邻近上下文或压缩后的全文上下文，避免超出模型上下文窗口。
- 严格保持字幕编号、条目数量和时间轴不变。

---

## 7. 模型生命周期状态机

```text
IDLE
  → SEPARATING
  → UNLOAD_SEPARATOR
  → TRANSCRIBING
  → UNLOAD_ASR
  → TRANSLATING
  → UNLOAD_TRANSLATOR
  → EXPORTING
  → COMPLETED
```

异常路径：

```text
任意状态 → CANCELLING/FAILED → STOP_ACTIVE_PROCESS → CLEAN_TEMP → IDLE
```

必须满足：

- 同一时刻最多存在一个重型本地模型进程。
- 人声分离结束后才允许加载 ASR。
- ASR 全部结束并确认进程退出后才允许加载本地翻译模型。
- 关闭应用时终止所有子进程。
- 正常、失败、取消和超时都执行相同的清理逻辑。

---

## 8. UI 重新设计

### 8.1 首页

- 文件拖拽与批量选择。
- 文件名、类型、大小、当前状态和输出路径。
- 处理方式：仅转录 / 转录并翻译。
- 目标语言。
- 导出格式：SRT / LRC。
- 内容模式：双语 / 仅原文 / 仅译文。
- 进度、当前阶段、日志、取消按钮。

交互约束：

- 选择“仅转录”时禁用翻译相关控件，但不改变用户原有选择。
- SRT/LRC 输入自动跳过音频预处理和 ASR。
- 启用人声分离但未配置 ONNX 模型时，开始前直接提示。

### 8.2 全局设置

- FFmpeg 路径。
- CrispASR 路径。
- llama-server 路径。
- 默认输出位置：与源文件相同 / 自定义目录。
- 主题、语言、完成通知和自动打开目录。

### 8.3 转录设置

音频预处理：

- 自动人声分离开关。
- UVR/MDX ONNX 模型路径。
- 模型目标：伴奏 / 人声。

ASR：

- Whisper large-v3-turbo / large-v3 / medium 模型。
- Silero VAD 本地模型。
- Backend：固定为 whisper。
- 识别语言：自动或指定。
- VAD 参数。
- 最大生成 token、频率惩罚和自定义参数。

### 8.4 翻译设置

- 本地 / 在线引擎。
- 翻译模型路径与 GPU 参数。
- API 地址、密钥和模型列表。
- Temperature、批量大小、提示词。
- “完成后自动卸载”固定启用并作为只读说明展示。

---

## 9. 配置模型

新增或保留以下关键配置：

```text
ffmpeg_path
crispasr_path
llama_server_path
output_directory_mode = source | custom
output_directory

vocal_separation_enabled
vocal_separation_model_path
vocal_separation_model_target = instrumental | vocals

asr_backend
asr_whisper_model_path
asr_qwen3_model_path
asr_qwen3_aligner_model_path
asr_language
asr_vad_enabled
asr_vad_model_path
asr_vad_min_silence_ms
asr_device
asr_whisper_extra_args
asr_qwen3_extra_args

translation_engine = local | online
translation_model_path
translation_gpu_layers
translation_context_size
translation_port
api_base_url
api_key
api_model
batch_size
temperature
translation_prompt
```

旧版本的 llama.cpp ASR 主模型/mmproj 配置不再读取；安装器会清理这些旧键。未来重新兼容时另行设计迁移。

---

## 10. 建议项目结构

```text
VoiceTranslator/
├── main.py
├── app/
│   ├── config.py
│   ├── common/
│   ├── models/
│   ├── core/
│   │   ├── pipeline.py
│   │   ├── file_handler.py
│   │   ├── audio_normalizer.py
│   │   ├── vocal_separator.py
│   │   ├── crispasr_engine.py
│   │   ├── translator.py
│   │   ├── llama_server_manager.py
│   │   └── subtitle_parser.py
│   └── views/
│       ├── main_window.py
│       ├── home_interface.py
│       ├── general_settings.py
│       ├── asr_settings.py
│       ├── translation_settings.py
│       └── about_interface.py
├── resources/
├── tests/
└── tools/
```

重构时应清理当前同名 `.py` 文件与同名 package 并存的问题，确保每个模块只有一个权威实现。

---

## 11. 错误处理

| 场景 | 行为 |
|:---|:---|
| FFmpeg 不存在 | 开始前阻止任务并定位到全局设置 |
| 分离模型不存在 | 仅在启用自动分离时阻止任务 |
| 分离失败 | 清理临时输出，不启动 ASR |
| CrispASR/模型/Aligner 不存在 | 开始前阻止任务并指出缺失项 |
| ASR 生成空字幕 | 标记该文件失败，不进入翻译 |
| 本地翻译服务启动超时 | 终止进程并保留原文字幕 |
| 在线 API 失败 | 支持有限次数重试，最终保留原文和中间数据 |
| 用户取消 | 终止当前进程、释放模型、删除临时文件 |
| 输出重名 | 默认生成 `_1`、`_2` 后缀，不覆盖原文件 |

---

## 12. 测试与验收

### 12.1 自动测试

- 文件类型识别。
- FFmpeg 命令参数。
- 人声分离模型目标与输出轨选择。
- 人声分离结束后才启动 ASR。
- CrispASR 命令构造。
- VAD/Aligner 参数传递。
- SRT/LRC 解析、合并和六种导出组合。
- 全批转录完成后才调用 Translator。
- 成功、失败、取消时的模型卸载顺序。
- 配置迁移。
- “仅转录”不修改内容模式。
- 源目录与自定义目录输出。

### 12.2 实机测试矩阵

1. 纯对白 WAV。
2. 带轻微背景音乐的音频，不启用分离。
3. 音乐明显覆盖对白的音频，启用 UVR 分离。
4. 长视频与多段对白。
5. 日语动画对白。
6. SRT/LRC 直接翻译。
7. 批量混合输入。
8. 转录中取消、分离中取消、翻译中取消。
9. 低显存环境下确认三个模型不同时驻留。

### 12.3 验收标准

- 输出字幕具有逐句开始和结束时间，而不是整段单一时间轴。
- 带背景音乐样本启用分离后，识别错误率有可感知下降。
- 批次中最后一个文件转录完成前，翻译模型不得启动。
- 每个阶段结束后，对应进程消失且 GPU 显存释放。
- 取消任务后 10 秒内无残留子进程。
- 源文件和源目录不出现临时 WAV、分离轨或缓存 JSON。
- SRT/LRC 时间轴单调、无负数、无重复编号。

---

## 13. 开发阶段

### Phase 0：代码基线整理

- 清理同名模块重复实现。
- 保留上游许可证和必要资产。
- 固化现有 18 项测试。

### Phase 1：CrispASR 转录核心

- 新增 CrispASREngine。
- 接入 Whisper、Silero VAD 和原生时间戳。
- 将 CrispASR SRT 转换为统一 segment 数据。
- 移除正式管线对 llama.cpp ASR API 的依赖。

### Phase 2：音频预处理完善

- 完成分离后 16 kHz 单声道规范化。
- 增加 ONNX 模型目标说明和输出试听验证。
- 完善取消、超时和临时文件清理。

### Phase 3：严格串行批处理

- 全批次预处理。
- 全批次转录。
- ASR 卸载屏障。
- 全批次翻译。
- 翻译卸载屏障。

### Phase 4：UI 与配置迁移

- 全局路径重新分组。
- Whisper/CrispASR/VAD 设置。
- 旧 ASR 配置迁移提示。
- 首页阶段状态展示。

### Phase 5：质量与发布

- 完成自动测试和实机矩阵。
- 增加一键环境检查。
- 打包时包含必要运行库，不打包模型权重。
- 编写模型下载与选择指南。

---

## 14. 当前状态与下一步

当前代码已经具备：

- QFluentWidgets 基础 UI。
- 批量文件、SRT/LRC 和导出。
- Whisper large-v3-turbo Q5 + CrispASR CUDA 正式转录路径。
- Silero VAD、本地 SRT 时间轴和 Qwen3 兼容后端。
- llama-server 本地翻译与在线翻译。
- 自动模型卸载。
- 可选 UVR/MDX 人声分离及 DirectML 环境。
- 源目录输出和仅转录 UI 修复。
- 一键 Whisper 运行时安装和检查脚本。
- 20 项通过的自动测试。
- RTX 3060 Laptop GPU 真实 CUDA 转录、SRT 导出和进程卸载验证。

尚未完成的关键工作：

1. 使用真实日语动画/影视样本进行逐句时间轴与强背景音乐测试。
2. 准备并验证合适的 UVR/MDX ONNX 人声分离模型。
3. 根据真实素材结果增加字幕长度约束、重复抑制和低置信度重试。
4. 清理临时兼容阶段产生的重复模块结构。

建议下一实施目标：用用户的动画 PV 素材完成 Whisper Turbo、不开分离和开启分离三组端到端对比。
