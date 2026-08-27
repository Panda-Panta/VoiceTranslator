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
    """JSON-oriented translator for general OpenAI-compatible APIs."""

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
                f"完整上下文（仅用于理解）：\n{context}\n\n"
                f"本批待翻译 JSON：\n{json.dumps(payload, ensure_ascii=False)}\n"
                '只返回 JSON 数组，每项为 {"id": 数字, "translation": "译文"}。'
            )
            content = self._complete(
                [
                    {"role": "system", "content": self.system_prompt.format(target_language=target_lang)},
                    {"role": "user", "content": user_prompt},
                ]
            )
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

    def _complete(self, messages: list[dict[str, str]]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        return (response.choices[0].message.content or "").strip()

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
    """Translation-model prompt path, compatible with Tencent Hy-MT2 GGUF."""

    _DELIMITER = "<|VT_SEGMENT|>"

    def __init__(self, base_url: str, model: str = "local-model", **kwargs: Any) -> None:
        super().__init__(base_url=f"{base_url.rstrip('/')}/v1", api_key="local", model=model, **kwargs)

    def translate(
        self,
        segments: list[TranscriptionSegment],
        source_lang: str,
        target_lang: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[TranscriptionSegment]:
        if not segments:
            return segments
        context = "\n".join(item.text for item in segments)
        translated = 0
        for offset in range(0, len(segments), self.batch_size):
            batch = segments[offset : offset + self.batch_size]
            translations = self._translate_local_batch(batch, context, target_lang)
            for item, value in zip(batch, translations, strict=True):
                item.translated_text = value.strip()
            translated += len(batch)
            if progress_callback:
                progress_callback(translated, len(segments))
        return segments

    def _translate_local_batch(
        self,
        batch: list[TranscriptionSegment],
        context: str,
        target_lang: str,
    ) -> list[str]:
        if len(batch) == 1:
            return [self._translate_one(batch[0].text, context, target_lang)]
        source = f"\n{self._DELIMITER}\n".join(item.text for item in batch)
        prompt = (
            f"背景信息：\n{context}\n\n"
            f"请将以下文本准确翻译为{target_lang}。只需要输出翻译后的结果，不要额外解释。\n"
            f"你必须在译文中保留数量和位置完全相同的分隔符 {self._DELIMITER}，不要翻译或转义该符号。\n\n"
            f"{source}"
        )
        content = self._local_complete(prompt)
        parts = [part.strip() for part in content.split(self._DELIMITER)]
        if len(parts) == len(batch) and all(
            self._valid_translation(item.text, part) for item, part in zip(batch, parts, strict=True)
        ):
            return parts
        # Small translation models occasionally drop delimiters. Retrying each
        # segment is slower but prevents subtitle alignment corruption.
        return [self._translate_one(item.text, context, target_lang) for item in batch]

    def _translate_one(self, text: str, context: str, target_lang: str) -> str:
        prompt = (
            f"将下面这一条字幕准确翻译成{target_lang}。只输出译文，不要解释，不要复述要求：\n{text}"
        )
        result = self._clean_local_translation(self._local_complete(prompt))
        if not self._valid_translation(text, result):
            raise RuntimeError(f"本地翻译模型返回了异常长度或多行结果：{result[:120]}")
        return result

    @classmethod
    def _valid_translation(cls, source: str, value: str) -> bool:
        candidate = value.strip()
        if not candidate or cls._DELIMITER in candidate or "待翻译" in candidate:
            return False
        if len([line for line in candidate.splitlines() if line.strip()]) > 2:
            return False
        return len(candidate) <= max(40, len(source.strip()) * 4)

    @staticmethod
    def _clean_local_translation(value: str) -> str:
        candidate = value.strip().strip("`\"'")
        candidate = re.sub(r"</?待翻译>", "", candidate).strip()
        candidate = re.sub(r"^(?:译文|翻译结果)\s*[：:]\s*", "", candidate).strip()
        return candidate

    def _local_complete(self, prompt: str) -> str:
        # Hy-MT2 has no default system prompt; use one user message and its
        # recommended sampling controls.
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            extra_body={"top_p": 0.6, "top_k": 20, "repeat_penalty": 1.05},
        )
        return (response.choices[0].message.content or "").strip()


class OnlineTranslator(OpenAICompatibleTranslator):
    @staticmethod
    def list_models(base_url: str, api_key: str) -> list[str]:
        client = OpenAI(base_url=base_url.rstrip("/"), api_key=api_key)
        return sorted(item.id for item in client.models.list().data)


__all__ = [
    "LocalTranslator",
    "OnlineTranslator",
    "OpenAICompatibleTranslator",
    "TranslatorBase",
]
