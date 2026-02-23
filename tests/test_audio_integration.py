from __future__ import annotations

import os
from pathlib import Path

import pytest

from italki_anki.audio import PollyAudioProvider
from italki_anki.tone_model import (
    ToneModelError,
    classify_second_syllable_tone_3_or_4,
    ffmpeg_available,
    second_syllable_terminal_delta_hz,
)

_ENABLE_ENV = "ITALKI_RUN_POLLY_PRONUNCIATION_TEST"

if os.getenv(_ENABLE_ENV, "").lower() not in {"1", "true", "yes"}:
    pytest.skip(
        f"Set {_ENABLE_ENV}=1 to run live Polly pronunciation integration tests.",
        allow_module_level=True,
    )

if not ffmpeg_available():
    pytest.skip(
        "ffmpeg is required for live tone contour verification tests.",
        allow_module_level=True,
    )


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _resolve_polly_region() -> str:
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"


def test_polly_ssml_tone_can_be_verified_by_tone_model(tmp_path):
    provider = PollyAudioProvider(
        output_dir=str(tmp_path),
        region_name=_resolve_polly_region(),
    )

    filename_tone4 = provider.create_audio("长假", pinyin="cháng jià")
    filename_tone3 = provider.create_audio("长假", pinyin="cháng jiǎ")

    tone4_audio = _read_bytes(tmp_path / filename_tone4)
    tone3_audio = _read_bytes(tmp_path / filename_tone3)

    # Confirm AWS account can synthesize both files before acoustic verification.
    assert len(tone4_audio) > 0
    assert len(tone3_audio) > 0
    assert tone4_audio != tone3_audio, "Polly returned identical audio for tone-3 and tone-4 hints"

    tone4_delta = second_syllable_terminal_delta_hz(tone4_audio)
    tone3_delta = second_syllable_terminal_delta_hz(tone3_audio)

    detected_tone4 = classify_second_syllable_tone_3_or_4(tone4_audio)
    detected_tone3 = classify_second_syllable_tone_3_or_4(tone3_audio)

    assert detected_tone4 == 4
    assert detected_tone3 == 3
    assert tone3_delta > tone4_delta


def test_tone_model_raises_for_non_speech_audio():
    with pytest.raises(ToneModelError):
        second_syllable_terminal_delta_hz(b"\x00" * 32, audio_format="wav")
