[CmdletBinding()]
param(
    [ValidateSet("cuda", "vulkan", "cpu")]
    [string]$Runtime = "cuda",
    [ValidateSet("large-v2-q8_0", "large-v2-q5_0", "large-v2", "large-v3-q5_0", "large-v3-turbo-q5_0")]
    [string]$Model = "large-v2-q8_0",
    [string]$CrispASRVersion = "v0.8.28",
    [string]$RuntimeRoot = "",
    [switch]$SkipAppConfig
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
if (-not $RuntimeRoot) {
    $RuntimeRoot = Join-Path $PSScriptRoot "..\runtime\whisper"
}

function Download-File {
    param([string]$Uri, [string]$Destination, [long]$MinimumBytes)
    if ((Test-Path -LiteralPath $Destination) -and (Get-Item -LiteralPath $Destination).Length -ge $MinimumBytes) {
        Write-Host "已存在，跳过下载：$Destination"
        return
    }
    Write-Host "正在下载：$Uri"
    $partialPath = "$Destination.partial"
    Remove-Item -LiteralPath $partialPath -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $partialPath
    $size = (Get-Item -LiteralPath $partialPath).Length
    if ($size -lt $MinimumBytes) {
        throw "下载文件大小异常：$partialPath ($size bytes)"
    }
    Move-Item -LiteralPath $partialPath -Destination $Destination -Force
}

function Set-ConfigValue {
    param([object]$Config, [string]$Name, [object]$Value)
    if ($null -eq $Config.PSObject.Properties[$Name]) {
        $Config | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    } else {
        $Config.$Name = $Value
    }
}

$runtimePath = [IO.Path]::GetFullPath($RuntimeRoot)
$binPath = Join-Path $runtimePath "bin"
$modelPath = Join-Path $runtimePath "models"
$downloadPath = Join-Path $runtimePath "downloads"
New-Item -ItemType Directory -Force -Path $binPath, $modelPath, $downloadPath | Out-Null

$assetName = switch ($Runtime) {
    "cuda" { "crispasr-windows-x86_64-cuda.zip" }
    "vulkan" { "crispasr-windows-x86_64-vulkan.zip" }
    default { "crispasr-windows-x86_64.zip" }
}
$archivePath = Join-Path $downloadPath $assetName
$releaseUrl = "https://github.com/CrispStrobe/CrispASR/releases/download/$CrispASRVersion/$assetName"
$crispasrExe = Get-ChildItem -LiteralPath $binPath -Filter "crispasr.exe" -File -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($null -eq $crispasrExe) {
    Download-File $releaseUrl $archivePath 10000000
    Expand-Archive -LiteralPath $archivePath -DestinationPath $binPath -Force
    Remove-Item -LiteralPath $archivePath -Force
    $crispasrExe = Get-ChildItem -LiteralPath $binPath -Filter "crispasr.exe" -File -Recurse |
        Select-Object -First 1
}
if ($null -eq $crispasrExe) {
    throw "CrispASR 压缩包中没有 crispasr.exe"
}

$modelFile = switch ($Model) {
    "large-v2-q8_0" { "ggml-large-v2-q8_0.bin" }
    "large-v2-q5_0" { "ggml-large-v2-q5_0.bin" }
    "large-v3-q5_0" { "ggml-large-v3-q5_0.bin" }
    "large-v3-turbo-q5_0" { "ggml-large-v3-turbo-q5_0.bin" }
    default { "ggml-large-v2.bin" }
}
$whisperModel = Join-Path $modelPath $modelFile
$modelUrl = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$modelFile"
Download-File $modelUrl $whisperModel 100000000

$vadModel = Join-Path $modelPath "ggml-silero-v6.2.0.bin"
$vadUrl = "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin"
Download-File $vadUrl $vadModel 500000

Write-Host "正在验证 CrispASR Whisper 后端"
$backendOutput = & $crispasrExe.FullName --list-backends 2>&1
if ($LASTEXITCODE -ne 0 -or ($backendOutput -join [Environment]::NewLine) -notmatch "(?im)^\s*whisper\b") {
    throw "CrispASR 未能正常列出 Whisper 后端"
}

$manifest = [ordered]@{
    installed_at = (Get-Date).ToString("o")
    crispasr_version = $CrispASRVersion
    runtime = $Runtime
    model = $Model
    crispasr_path = $crispasrExe.FullName
    whisper_model_path = $whisperModel
    vad_model_path = $vadModel
}
$manifestPath = Join-Path $runtimePath "runtime.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json), $utf8NoBom)

if (-not $SkipAppConfig) {
    $appDataRoot = [Environment]::GetFolderPath("ApplicationData")
    $configPath = Join-Path $appDataRoot "VoiceTranslator\config.json"
    if (Test-Path -LiteralPath $configPath) {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding utf8 | ConvertFrom-Json
    } else {
        $config = [pscustomobject]@{}
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $configPath) | Out-Null
    }
    Set-ConfigValue $config "crispasr_path" $crispasrExe.FullName
    Set-ConfigValue $config "asr_whisper_model_path" $whisperModel
    Set-ConfigValue $config "asr_vad_enabled" $true
    Set-ConfigValue $config "asr_vad_model_path" $vadModel
    Set-ConfigValue $config "asr_timestamps" $true
    $config.PSObject.Properties.Remove("asr_mmproj_path")
    $config.PSObject.Properties.Remove("asr_port")
    $config.PSObject.Properties.Remove("asr_model_size")
    $config.PSObject.Properties.Remove("asr_model_path")
    $config.PSObject.Properties.Remove("asr_aligner_model_path")
    $config.PSObject.Properties.Remove("asr_extra_args")
    $config.PSObject.Properties.Remove("asr_backend")
    $config.PSObject.Properties.Remove("asr_qwen3_model_path")
    $config.PSObject.Properties.Remove("asr_qwen3_aligner_model_path")
    $config.PSObject.Properties.Remove("asr_qwen3_lid_model_path")
    $config.PSObject.Properties.Remove("asr_qwen3_extra_args")
    [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 10), $utf8NoBom)
    Write-Host "已更新应用配置：$configPath"
}

Write-Host ""
Write-Host "Whisper 环境准备完成"
Write-Host "CrispASR: $($crispasrExe.FullName)"
Write-Host "Whisper:   $whisperModel"
Write-Host "Silero:    $vadModel"
Write-Host "Manifest:  $manifestPath"
