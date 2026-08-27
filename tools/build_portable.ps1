[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$LlamaRoot = "",
    [string]$TranslationModel = "",
    [string]$FfmpegRoot = "",
    [string]$PackageName = "VoiceTranslator-Portable-CUDA",
    [switch]$SkipBuild,
    [switch]$SkipArchive
)

$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$releaseRoot = Join-Path $projectRoot "release"
$packageRoot = Join-Path $releaseRoot $PackageName
$archivePath = Join-Path $releaseRoot "$PackageName.zip"
if (-not $LlamaRoot -or -not $TranslationModel -or -not $FfmpegRoot) {
    throw "请通过 -LlamaRoot、-TranslationModel 和 -FfmpegRoot 指定整合包所需的本地运行时与模型路径"
}
if (-not $Python) {
    $Python = Join-Path $projectRoot ".build-venv\Scripts\python.exe"
}

$crispRoot = Join-Path $projectRoot "runtime\whisper\bin\crispasr-windows-x86_64-cuda"
$whisperModels = Join-Path $projectRoot "runtime\whisper\models"
$separationModel = Join-Path $projectRoot "runtime\separation\models\Kim_Vocal_2.onnx"
$requiredFiles = @(
    $Python,
    (Join-Path $LlamaRoot "llama-server.exe"),
    $TranslationModel,
    (Join-Path $FfmpegRoot "ffmpeg.exe"),
    (Join-Path $FfmpegRoot "ffprobe.exe"),
    (Join-Path $crispRoot "crispasr.exe"),
    (Join-Path $whisperModels "ggml-large-v2-q8_0.bin"),
    (Join-Path $whisperModels "ggml-large-v3-q5_0.bin"),
    (Join-Path $whisperModels "ggml-large-v3-turbo-q5_0.bin"),
    (Join-Path $whisperModels "ggml-silero-v6.2.0.bin"),
    $separationModel
)
foreach ($path in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "缺少整合包文件：$path"
    }
}

Push-Location $projectRoot
try {
    if (-not $SkipBuild) {
        & $Python -m PyInstaller --clean --noconfirm separate.spec --distpath .
        if ($LASTEXITCODE -ne 0) { throw "人声分离程序构建失败" }
        & $Python -m PyInstaller --clean --noconfirm app.spec
        if ($LASTEXITCODE -ne 0) { throw "桌面程序构建失败" }
    }

    $builtApp = Join-Path $projectRoot "dist\VoiceTranslator"
    if (-not (Test-Path -LiteralPath (Join-Path $builtApp "VoiceTranslator.exe"))) {
        throw "找不到构建后的 VoiceTranslator.exe"
    }

    New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
    $resolvedRelease = [IO.Path]::GetFullPath($releaseRoot)
    $resolvedPackage = [IO.Path]::GetFullPath($packageRoot)
    if (-not $resolvedPackage.StartsWith($resolvedRelease + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝清理 release 目录之外的路径：$resolvedPackage"
    }
    if (Test-Path -LiteralPath $packageRoot) {
        Remove-Item -LiteralPath $packageRoot -Recurse -Force
    }
    Copy-Item -LiteralPath $builtApp -Destination $packageRoot -Recurse

    $runtimeLlama = Join-Path $packageRoot "runtime\llama"
    $runtimeWhisper = Join-Path $packageRoot "runtime\whisper\bin"
    $runtimeFfmpeg = Join-Path $packageRoot "runtime\ffmpeg"
    $modelWhisper = Join-Path $packageRoot "models\whisper"
    $modelSeparation = Join-Path $packageRoot "models\separation"
    $modelTranslation = Join-Path $packageRoot "models\translation"
    New-Item -ItemType Directory -Force -Path $runtimeLlama, $runtimeWhisper, $runtimeFfmpeg, $modelWhisper, $modelSeparation, $modelTranslation | Out-Null

    Copy-Item -Path (Join-Path $LlamaRoot "*") -Destination $runtimeLlama -Recurse -Force
    Copy-Item -Path (Join-Path $crispRoot "*") -Destination $runtimeWhisper -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $FfmpegRoot "ffmpeg.exe"), (Join-Path $FfmpegRoot "ffprobe.exe") -Destination $runtimeFfmpeg
    Copy-Item -LiteralPath (Join-Path $whisperModels "ggml-large-v2-q8_0.bin") -Destination $modelWhisper
    Copy-Item -LiteralPath (Join-Path $whisperModels "ggml-large-v3-q5_0.bin") -Destination $modelWhisper
    Copy-Item -LiteralPath (Join-Path $whisperModels "ggml-large-v3-turbo-q5_0.bin") -Destination $modelWhisper
    Copy-Item -LiteralPath (Join-Path $whisperModels "ggml-silero-v6.2.0.bin") -Destination $modelWhisper
    Copy-Item -LiteralPath $separationModel -Destination $modelSeparation
    Copy-Item -LiteralPath $TranslationModel -Destination $modelTranslation
    Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $packageRoot

    [IO.File]::WriteAllText((Join-Path $packageRoot "portable.flag"), "VoiceTranslator portable mode" + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    $config = [ordered]@{
        theme = "system"
        theme_color = "#009faa"
        ui_font_scale = 125
        language = "zh_CN"
        ffmpeg_path = "runtime\ffmpeg\ffmpeg.exe"
        output_directory = ""
        output_directory_mode = "source"
        notify_when_done = $true
        open_output_directory = $false
        llama_server_path = "runtime\llama\llama-server.exe"
        crispasr_path = "runtime\whisper\bin\crispasr.exe"
        asr_model_path = "models\whisper\ggml-large-v2-q8_0.bin"
        asr_gpu_layers = 999
        asr_threads = 20
        asr_timestamps = $true
        asr_language = "auto"
        asr_vad_enabled = $true
        asr_vad_model_path = "models\whisper\ggml-silero-v6.2.0.bin"
        asr_vad_min_silence_ms = 500
        asr_vad_speech_pad_ms = 150
        asr_split_on_punctuation = $false
        subtitle_resegment_enabled = $true
        subtitle_max_chars = 28
        subtitle_max_duration = 6.0
        subtitle_merge_gap_ms = 250
        asr_device = 0
        asr_extra_args = ""
        vocal_separation_enabled = $true
        vocal_separation_model_path = "models\separation\Kim_Vocal_2.onnx"
        translation_engine = "local"
        translation_model_path = "models\translation\Hy-MT2-1.8B-Q8_0.gguf"
        translation_gpu_layers = 999
        translation_context_size = 8192
        translation_port = 8080
        api_base_url = "https://api.openai.com/v1"
        api_key = ""
        api_model = ""
        temperature = 0.2
        translation_prompt = ""
        batch_size = 10
        server_start_timeout = 120.0
        auto_unload_models = $true
    }
    [IO.File]::WriteAllText((Join-Path $packageRoot "config.json"), ($config | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))

    $instructions = @(
        "VoiceTranslator CUDA 解压即用整合包",
        "",
        "1. 完整解压 ZIP，双击 VoiceTranslator.exe。",
        "2. 默认使用 Whisper large-v2 Q8、Silero VAD、Kim Vocal 2 和 Hy-MT2 1.8B Q8。",
        "3. 可在转录设置中切换 models\whisper 下的 large-v3 或 large-v3-turbo。",
        "4. 需要支持 CUDA 12/13 的 NVIDIA 驱动；所有模型路径均为包内相对路径。",
        "5. config.json 位于程序目录，不会修改 %APPDATA% 中的现有配置。"
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText((Join-Path $packageRoot "使用说明.txt"), $instructions, [Text.UTF8Encoding]::new($true))

    $manifest = Get-ChildItem -LiteralPath $packageRoot -Recurse -File | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($packageRoot.Length + 1)
            size = $_.Length
        }
    }
    [IO.File]::WriteAllText((Join-Path $packageRoot "package-manifest.json"), ($manifest | ConvertTo-Json -Depth 4), [Text.UTF8Encoding]::new($false))

    if (-not $SkipArchive) {
        & $Python tools\create_portable_zip.py $packageRoot $archivePath
        if ($LASTEXITCODE -ne 0) { throw "整合包压缩失败" }
        (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash | Set-Content -LiteralPath "$archivePath.sha256" -Encoding ascii
    }

    Write-Host "PACKAGE_ROOT=$packageRoot"
    if (-not $SkipArchive) {
        Write-Host "ARCHIVE=$archivePath"
    }
} finally {
    Pop-Location
}
