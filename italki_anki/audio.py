from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape


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
    return " ".join(pinyin.split())


def build_polly_phoneme_ssml(text: str, pinyin: str) -> str:
    text_escaped = escape(text)
    pinyin_escaped = escape(pinyin)
    return (
        "<speak>"
        f"<phoneme alphabet=\"x-amazon-pinyin\" ph=\"{pinyin_escaped}\">{text_escaped}</phoneme>"
        "</speak>"
    )
