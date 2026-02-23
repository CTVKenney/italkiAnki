from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape

_MARKED_VOWELS = {
    "ā": ("a", "1"),
    "á": ("a", "2"),
    "ǎ": ("a", "3"),
    "à": ("a", "4"),
    "ē": ("e", "1"),
    "é": ("e", "2"),
    "ě": ("e", "3"),
    "è": ("e", "4"),
    "ī": ("i", "1"),
    "í": ("i", "2"),
    "ǐ": ("i", "3"),
    "ì": ("i", "4"),
    "ō": ("o", "1"),
    "ó": ("o", "2"),
    "ǒ": ("o", "3"),
    "ò": ("o", "4"),
    "ū": ("u", "1"),
    "ú": ("u", "2"),
    "ǔ": ("u", "3"),
    "ù": ("u", "4"),
    "ǖ": ("v", "1"),
    "ǘ": ("v", "2"),
    "ǚ": ("v", "3"),
    "ǜ": ("v", "4"),
}


@dataclass
class AudioProvider:
    output_dir: str

    def create_audio(self, text: str, pinyin: str | None = None) -> str:
        raise NotImplementedError


@dataclass
class PollyAudioProvider(AudioProvider):
    voice_id: str = "Zhiyu"
    region_name: str | None = None

    def create_audio(self, text: str, pinyin: str | None = None) -> str:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("boto3 is required for Polly audio") from exc

        os.makedirs(self.output_dir, exist_ok=True)
        normalized_pinyin = normalize_pinyin_hint(pinyin)
        filename = deterministic_audio_filename(text, pronunciation_hint=normalized_pinyin)
        path = os.path.join(self.output_dir, filename)
        if os.path.exists(path):
            return filename

        text_payload = text
        text_type = "text"
        if normalized_pinyin:
            text_payload = build_polly_phoneme_ssml(text, normalized_pinyin)
            text_type = "ssml"

        client_kwargs = {}
        if self.region_name:
            client_kwargs["region_name"] = self.region_name
        client = boto3.client("polly", **client_kwargs)
        response = client.synthesize_speech(
            Text=text_payload,
            TextType=text_type,
            OutputFormat="mp3",
            VoiceId=self.voice_id,
            LanguageCode="cmn-CN",
        )
        stream = response.get("AudioStream")
        if stream is None:
            raise RuntimeError("Polly did not return audio stream")
        with open(path, "wb") as handle:
            handle.write(stream.read())
        return filename


@dataclass
class NullAudioProvider(AudioProvider):
    def create_audio(self, text: str, pinyin: str | None = None) -> str:
        del text
        del pinyin
        return ""


def deterministic_audio_filename(
    text: str,
    suffix: Optional[str] = None,
    pronunciation_hint: str | None = None,
) -> str:
    normalized = text.strip()
    normalized_hint = normalize_pinyin_hint(pronunciation_hint)
    if normalized_hint:
        normalized = f"{normalized}|{normalized_hint}"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    extension = suffix or "mp3"
    return f"audio_{digest}.{extension}"


def normalize_pinyin_hint(pinyin: str | None) -> str:
    if not pinyin:
        return ""
    normalized = " ".join(pinyin.split())
    if not normalized:
        return ""
    return "-".join(_normalize_pinyin_syllable(token) for token in normalized.split(" "))


def _normalize_pinyin_syllable(token: str) -> str:
    lowered = token.lower().replace("ü", "v")
    if any(character.isdigit() for character in lowered):
        return lowered

    tone = ""
    transformed: list[str] = []
    tone_marks_seen = 0
    for character in token:
        lower_character = character.lower()
        if lower_character in _MARKED_VOWELS:
            base, marked_tone = _MARKED_VOWELS[lower_character]
            transformed.append(base)
            tone = marked_tone
            tone_marks_seen += 1
            continue
        if lower_character == "ü":
            transformed.append("v")
        else:
            transformed.append(lower_character)

    if not tone:
        return "".join(transformed)
    if tone_marks_seen == 1:
        return "".join(transformed) + tone
    # Fallback for compact multi-syllable tokens; keep each tone where it appears.
    fallback: list[str] = []
    for character in token:
        lower_character = character.lower()
        if lower_character in _MARKED_VOWELS:
            base, marked_tone = _MARKED_VOWELS[lower_character]
            fallback.append(base + marked_tone)
            continue
        if lower_character == "ü":
            fallback.append("v")
        else:
            fallback.append(lower_character)
    return "".join(fallback)


def build_polly_phoneme_ssml(text: str, pinyin: str) -> str:
    text_escaped = escape(text)
    pinyin_escaped = escape(pinyin)
    return (
        "<speak>"
        f"<phoneme alphabet=\"x-amazon-pinyin\" ph=\"{pinyin_escaped}\">{text_escaped}</phoneme>"
        "</speak>"
    )
