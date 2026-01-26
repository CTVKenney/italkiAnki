from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterable, List, Sequence

import urllib.error
import urllib.request

from .models import ClassifiedItem, ItemType


@dataclass
class LLMClient:
    def classify(self, lines: Iterable[str], seed: int | None = None) -> List[ClassifiedItem]:
        raise NotImplementedError


@dataclass
class OpenAIClient(LLMClient):
    api_key: str
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"

    def classify(self, lines: Iterable[str], seed: int | None = None) -> List[ClassifiedItem]:
        payload = build_openai_payload(list(lines), model=self.model, seed=seed)
        response_payload = post_json(
            f"{self.base_url}/chat/completions",
            payload,
            api_key=self.api_key,
        )
        content = extract_openai_content(response_payload)
        return parse_classified_items(content)


@dataclass
class StubClient(LLMClient):
    """Stub LLM client for offline testing without API calls."""

    def classify(self, lines: Iterable[str], seed: int | None = None) -> List[ClassifiedItem]:
        items: List[ClassifiedItem] = []
        for line in lines:
            normalized = strip_parenthetical_gloss(line)
            if "=" in normalized:
                item_type = ItemType.GRAMMAR
            elif normalized.endswith(("？", "?")):
                item_type = ItemType.SENTENCE
            else:
                item_type = ItemType.VOCAB
            items.append(
                ClassifiedItem(
                    item_type=item_type,
                    simplified=normalized,
                    traditional=normalized,
                    pinyin="",
                    english="",
                    gloss=None,
                    measure_word=None,
                    measure_word_pinyin=None,
                )
            )
        return items


def strip_parenthetical_gloss(text: str) -> str:
    if text.endswith(")") and " (" in text:
        base, _, _ = text.rpartition(" (")
        return base
    return text


def openai_client_from_env() -> OpenAIClient:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return OpenAIClient(api_key=api_key, model=model, base_url=base_url)


def build_openai_payload(lines: Sequence[str], model: str, seed: int | None) -> dict:
    system_prompt = (
        "You are a Chinese study assistant. Return strict JSON with shape "
        "{\"items\": [ ... ]}. Each item must contain: item_type "
        "(vocabulary|grammar|sentence), simplified, traditional, pinyin "
        "(tone marked), english. Optional: gloss, measure_word, "
        "measure_word_pinyin. Classify each input line and remove noise. "
        "If a line contains a gloss in parentheses, treat it as guidance."
    )
    user_prompt = "Lines:\n" + "\n".join(f"- {line}" for line in lines)
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    if seed is not None:
        payload["seed"] = seed
    return payload


def extract_openai_content(payload: dict) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:  # pragma: no cover - defensive
        raise ValueError("Unexpected OpenAI response format") from exc
    if not isinstance(content, str):
        raise ValueError("OpenAI content must be a string")
    return content


def post_json(url: str, payload: dict, api_key: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status >= 400:
                raise RuntimeError(f"OpenAI request failed with status {response.status}")
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.code}") from exc
    return json.loads(raw)


def parse_classified_items(payload: str) -> List[ClassifiedItem]:
    data = json.loads(payload)
    if isinstance(data, dict):
        data = data.get("items")
    if not isinstance(data, list):
        raise ValueError("LLM response must be a list")
    items: List[ClassifiedItem] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("LLM entry must be object")
        item_type = ItemType(entry["item_type"])
        items.append(
            ClassifiedItem(
                item_type=item_type,
                simplified=entry["simplified"],
                traditional=entry["traditional"],
                pinyin=entry["pinyin"],
                english=entry["english"],
                gloss=entry.get("gloss"),
                measure_word=entry.get("measure_word"),
                measure_word_pinyin=entry.get("measure_word_pinyin"),
            )
        )
    return items
