from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Callable

from openai import OpenAI

from app.common.constants import DEFAULT_TRANSLATION_PROMPT
from app.models import TranscriptionSegment


class TranslatorBase(ABC):
    @abstractmethod
    def translate(
        self,
        segments: list[TranscriptionSegment],
        source_lang: str,
        target_lang: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[TranscriptionSegment]: ...


class OpenAICompatibleTranslator(TranslatorBase):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        batch_size: int = 10,
        temperature: float = 0.2,
        system_prompt: str = "",
        timeout: float = 180.0,
    ) -> None:
        self.client = OpenAI(base_url=base_url.rstrip("/"), api_key=api_key or "local", timeout=timeout)
        self.model = model
        self.batch_size = max(1, min(50, batch_size))
        self.temperature = max(0.0, min(2.0, temperature))
        self.system_prompt = system_prompt or DEFAULT_TRANSLATION_PROMPT

    def translate(
        self,
        segments: list[TranscriptionSegment],
        source_lang: str,
        target_lang: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[TranscriptionSegment]:
        if not segments:
            return segments
        context = "\n".join(f"{item.index}: {item.text}" for item in segments)
        translated = 0
        for offset in range(0, len(segments), self.batch_size):
            batch = segments[offset : offset + self.batch_size]
            payload = [{"id": item.index, "text": item.text} for item in batch]
            user_prompt = (
                f"源语言：{source_lang}\n目标语言：{target_lang}\n"
                "完整上下文如下（仅用于理解，不要全部翻译）：\n"
                f"{context}\n\n本批待翻译 JSON：\n{json.dumps(payload, ensure_ascii=False)}\n"
                '请返回 JSON 数组，每项严格为 {"id": 数字, "translation": "译文"}。'
            )
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt.format(target_language=target_lang)},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
            )
            content = response.choices[0].message.content or ""
            mapping = self._parse_translations(content)
            missing = []
            for item in batch:
                value = mapping.get(item.index, "").strip()
                if not value:
                    missing.append(item.index)
                item.translated_text = value
            if missing:
                raise RuntimeError(f"翻译响应缺少字幕编号：{missing}")
            translated += len(batch)
            if progress_callback:
                progress_callback(translated, len(segments))
        return segments

    @staticmethod
    def _parse_translations(content: str) -> dict[int, str]:
        candidate = content.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", candidate, flags=re.I | re.S)
        if fenced:
            candidate = fenced.group(1).strip()
        start, end = candidate.find("["), candidate.rfind("]")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"翻译模型未返回有效 JSON：{content[:200]}") from exc
        if not isinstance(data, list):
            raise RuntimeError("翻译响应必须是 JSON 数组")
        result: dict[int, str] = {}
        for row in data:
            if isinstance(row, dict) and "id" in row:
                value: Any = row.get("translation", row.get("text", ""))
                result[int(row["id"])] = str(value)
        return result


class LocalTranslator(OpenAICompatibleTranslator):
    def __init__(self, base_url: str, model: str = "local-model", **kwargs: Any) -> None:
        super().__init__(base_url=f"{base_url.rstrip('/')}/v1", api_key="local", model=model, **kwargs)


class OnlineTranslator(OpenAICompatibleTranslator):
    @staticmethod
    def list_models(base_url: str, api_key: str) -> list[str]:
        client = OpenAI(base_url=base_url.rstrip("/"), api_key=api_key)
        return sorted(item.id for item in client.models.list().data)
