from __future__ import annotations

import json
from pathlib import Path


class I18n:
    def __init__(self, language: str = "zh_CN") -> None:
        self.language = language
        path = Path(__file__).parent.parent / "resources" / "i18n" / f"{language}.json"
        try:
            self.messages = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.messages = {}

    def __call__(self, key: str, fallback: str | None = None) -> str:
        return str(self.messages.get(key, fallback or key))
