from __future__ import annotations

APP_NAME = "VoiceTranslator"
APP_VERSION = "1.1.0"
PROJECT_REPOSITORY_URL = "https://github.com/Panda-Panta/VoiceTranslator"
UPSTREAM_REPOSITORY_URL = "https://github.com/shinnpuru/VoiceTransl"

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"}
SUBTITLE_EXTENSIONS = {".srt"}
LYRICS_EXTENSIONS = {".lrc"}
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | SUBTITLE_EXTENSIONS | LYRICS_EXTENSIONS

LANGUAGES = ["简体中文", "English", "日本語", "한국어", "Français", "Deutsch", "Español", "Русский"]
DEFAULT_TRANSLATION_PROMPT = (
    "你是专业字幕译者。请准确、自然地将输入字幕翻译成{target_language}，保持语气、称谓和术语一致。"
    "只返回指定 JSON 格式，不要解释，不要遗漏或合并条目。"
)
