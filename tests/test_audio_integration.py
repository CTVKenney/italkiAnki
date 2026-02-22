from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
import urllib.error
import urllib.request

import pytest

from italki_anki.audio import PollyAudioProvider

_ENABLE_ENV = "ITALKI_RUN_POLLY_PRONUNCIATION_TEST"
_OPENAI_MODEL_ENV = "OPENAI_AUDIO_EVAL_MODEL"
_DEFAULT_OPENAI_AUDIO_MODEL = "gpt-4o-audio-preview"

if os.getenv(_ENABLE_ENV, "").lower() not in {"1", "true", "yes"}:
    pytest.skip(
        f"Set {_ENABLE_ENV}=1 to run live Polly pronunciation integration tests.",
        allow_module_level=True,
    )


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.fail(f"{name} must be set when {_ENABLE_ENV}=1")
    return value


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _extract_tone(response_text: str) -> int:
    compact = response_text.strip()
    if compact in {"3", "4"}:
        return int(compact)
    try:
        payload = json.loads(compact)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        tone = payload.get("tone")
        if tone in (3, 4):
            return int(tone)
        if isinstance(tone, str):
            match = re.search(r"\b([34])\b", tone)
            if match:
                return int(match.group(1))
    match = re.search(r"\b([34])\b", compact)
    if match:
        return int(match.group(1))
    raise AssertionError(f"Expected tone 3 or 4, got: {response_text!r}")


def _post_openai_chat_completions(payload: dict, api_key: str) -> dict:
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        if exc.fp is not None:
            body = exc.fp.read().decode("utf-8", errors="ignore")
        raise AssertionError(
            f"OpenAI audio eval request failed with HTTP {exc.code}: {body[:500]}"
        ) from None


def _detect_second_tone_from_audio(audio_bytes: bytes, *, model: str) -> int:
    api_key = _require_env("OPENAI_API_KEY")
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    prompt = (
        "Listen to this Mandarin audio. The phrase is two syllables and starts with 'chang2'. "
        "Decide whether the second syllable is tone 3 or tone 4 based only on the audio. "
        "Reply with a single character only: 3 or 4."
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": "mp3",
                        },
                    },
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 8,
    }
    response = _post_openai_chat_completions(payload, api_key)
    content = response["choices"][0]["message"]["content"]
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_value = part.get("text")
                if isinstance(text_value, str):
                    text_parts.append(text_value)
        content = " ".join(text_parts)
    if not isinstance(content, str):
        raise AssertionError(f"Unexpected OpenAI response content: {content!r}")
    return _extract_tone(content)


def _resolve_polly_region() -> str:
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"


def test_polly_ssml_tone_can_be_verified_by_audio_model(tmp_path):
    _require_env("OPENAI_API_KEY")
    model = os.getenv(_OPENAI_MODEL_ENV, _DEFAULT_OPENAI_AUDIO_MODEL)

    provider = PollyAudioProvider(
        output_dir=str(tmp_path),
        region_name=_resolve_polly_region(),
    )

    filename_tone4 = provider.create_audio("长假", pinyin="chángjià")
    filename_tone3 = provider.create_audio("长假", pinyin="chángjiǎ")

    tone4_audio = _read_bytes(tmp_path / filename_tone4)
    tone3_audio = _read_bytes(tmp_path / filename_tone3)

    # Confirm AWS account can synthesize both files before invoking OpenAI.
    assert len(tone4_audio) > 0
    assert len(tone3_audio) > 0

    detected_tone4 = _detect_second_tone_from_audio(
        tone4_audio,
        model=model,
    )
    detected_tone3 = _detect_second_tone_from_audio(
        tone3_audio,
        model=model,
    )

    assert detected_tone4 == 4
    assert detected_tone3 == 3
