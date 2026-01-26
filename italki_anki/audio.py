from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AudioProvider:
    output_dir: str

    def create_audio(self, text: str) -> str:
        raise NotImplementedError


@dataclass
class PollyAudioProvider(AudioProvider):
    voice_id: str = "Zhiyu"

    def create_audio(self, text: str) -> str:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("boto3 is required for Polly audio") from exc

        os.makedirs(self.output_dir, exist_ok=True)
        filename = deterministic_audio_filename(text)
        path = os.path.join(self.output_dir, filename)
        if os.path.exists(path):
            return filename
        client = boto3.client("polly")
        response = client.synthesize_speech(
            Text=text,
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
    def create_audio(self, text: str) -> str:
        return ""


def deterministic_audio_filename(text: str, suffix: Optional[str] = None) -> str:
    normalized = text.strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    extension = suffix or "mp3"
    return f"audio_{digest}.{extension}"
