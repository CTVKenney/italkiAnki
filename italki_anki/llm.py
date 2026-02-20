from __future__ import annotations

import json
import os
import random
import time
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
    max_lines: int = 20

    def classify(self, lines: Iterable[str], seed: int | None = None) -> List[ClassifiedItem]:
        all_lines = list(lines)
        results: List[ClassifiedItem] = []
        for chunk in chunk_lines(all_lines, self.max_lines):
            payload = build_openai_payload(chunk, model=self.model, seed=seed)
            response_payload = post_json(
                f"{self.base_url}/chat/completions",
                payload,
                api_key=self.api_key,
            )
            content = extract_openai_content(response_payload)
            results.extend(parse_classified_items(content))
        return results


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
    max_lines = int(os.getenv("OPENAI_MAX_LINES", "20"))
    return OpenAIClient(api_key=api_key, model=model, base_url=base_url, max_lines=max_lines)


def build_openai_payload(lines: Sequence[str], model: str, seed: int | None) -> dict:
    system_prompt = (
        "You are a Chinese study assistant. Return strict JSON with shape "
        "{\"items\": [ ... ]}. Each item must contain: item_type "
        "(vocabulary|grammar|sentence), simplified, traditional, pinyin "
        "(tone marked), english. Optional: gloss, measure_word, "
        "measure_word_pinyin. Exclude non-study noise such as channel names, "
        "labels like transcript/audio, timestamps, platform brands, speaker "
        "tags, social pleasantries (thanks/farewell to teacher), and other "
        "chat small talk. If uncertain, omit the item. Do not infer or invent "
        "measure words; only include measure_word fields when that measure "
        "word appears explicitly in the same input line. If a line contains a "
        "gloss in parentheses, treat it as guidance."
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
    max_retries = 6
    retryable_statuses = {429, 500, 502, 503}
    last_error: int | None = None
    last_error_detail = ""
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status >= 400:
                    raise RuntimeError(f"OpenAI request failed with status {response.status}")
                raw = response.read().decode("utf-8")
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            last_error = exc.code
            body_text = ""
            if exc.fp is not None:
                body_text = exc.fp.read().decode("utf-8", errors="ignore")
            detail = summarize_openai_error_body(body_text)
            if detail:
                last_error_detail = detail
            if exc.code not in retryable_statuses:
                if detail:
                    raise RuntimeError(f"OpenAI request failed: {exc.code} {detail}") from exc
                raise RuntimeError(f"OpenAI request failed: {exc.code}") from exc
            if attempt >= max_retries:
                break
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if retry_after:
                sleep_for = max(float(retry_after), 0.0)
            else:
                base = min(2**attempt, 30)
                sleep_for = min(base, 30) + random.random() * 0.5
            time.sleep(sleep_for)
        except urllib.error.URLError as exc:
            last_error = None
            raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc
    if last_error is not None:
        if last_error == 429:
            base = (
                "OpenAI request failed after retries: 429 "
                "(rate limit or insufficient quota). "
                "Check account usage/billing and retry."
            )
            if last_error_detail:
                return_detail = f"{base} Last error: {last_error_detail}"
                raise RuntimeError(return_detail)
            raise RuntimeError(base)
        if last_error_detail:
            raise RuntimeError(
                f"OpenAI request failed after retries: {last_error} {last_error_detail}"
            )
        raise RuntimeError(f"OpenAI request failed after retries: {last_error}")
    raise RuntimeError("OpenAI request failed after retries")


def summarize_openai_error_body(body_text: str) -> str:
    cleaned = body_text.strip()
    if not cleaned:
        return ""
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return cleaned[:200]
    if not isinstance(payload, dict):
        return cleaned[:200]
    error = payload.get("error")
    if not isinstance(error, dict):
        return cleaned[:200]
    parts: list[str] = []
    err_type = error.get("type")
    if isinstance(err_type, str) and err_type.strip():
        parts.append(err_type.strip())
    err_code = error.get("code")
    if isinstance(err_code, str) and err_code.strip() and err_code.strip() not in parts:
        parts.append(err_code.strip())
    message = error.get("message")
    if isinstance(message, str) and message.strip():
        parts.append(message.strip())
    if not parts:
        return cleaned[:200]
    return " | ".join(parts)[:200]


def chunk_lines(lines: Sequence[str], size: int) -> Iterable[List[str]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    for index in range(0, len(lines), size):
        yield list(lines[index : index + size])


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
