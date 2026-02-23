from __future__ import annotations

import math
import shutil
import subprocess
import sys
import wave
from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable


class ToneModelError(RuntimeError):
    """Raised when tone contour extraction cannot be completed."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def decode_audio_to_mono_samples(
    audio_bytes: bytes,
    *,
    audio_format: str = "mp3",
    sample_rate: int = 16_000,
) -> tuple[list[float], int]:
    if not ffmpeg_available():
        raise ToneModelError("ffmpeg is required for tone contour extraction")

    with TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        input_path = tmp / f"input.{audio_format}"
        output_path = tmp / "output.wav"
        input_path.write_bytes(audio_bytes)

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "wav",
            str(output_path),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ToneModelError(f"ffmpeg decode failed: {result.stderr.strip()[:300]}")

        with wave.open(str(output_path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            width = wav_file.getsampwidth()
            output_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            raw_frames = wav_file.readframes(frame_count)

    if channels != 1:
        raise ToneModelError(f"expected mono audio, got {channels} channels")
    if width != 2:
        raise ToneModelError(f"expected 16-bit PCM output, got sample width {width}")

    samples_i16 = array("h")
    samples_i16.frombytes(raw_frames)
    if samples_i16.itemsize != 2:
        raise ToneModelError("invalid PCM sample width")
    if sys.byteorder == "big":
        samples_i16.byteswap()
    samples = [value / 32768.0 for value in samples_i16]
    return samples, output_rate


def estimate_pitch_hz(
    frame: Iterable[float],
    sample_rate: int,
    *,
    min_hz: float = 70.0,
    max_hz: float = 400.0,
    min_energy: float = 1e-5,
    min_correlation: float = 0.3,
) -> float | None:
    values = list(frame)
    if len(values) < 4:
        return None

    mean = sum(values) / len(values)
    windowed = [
        (values[index] - mean)
        * (0.54 - 0.46 * math.cos((2 * math.pi * index) / (len(values) - 1)))
        for index in range(len(values))
    ]
    energy = sum(value * value for value in windowed) / len(windowed)
    if energy < min_energy:
        return None

    min_lag = max(1, int(sample_rate / max_hz))
    max_lag = min(len(windowed) - 1, int(sample_rate / min_hz))
    if max_lag <= min_lag:
        return None

    best_lag = 0
    best_corr = -1.0
    for lag in range(min_lag, max_lag + 1):
        numerator = 0.0
        energy_a = 0.0
        energy_b = 0.0
        for index in range(len(windowed) - lag):
            sample_a = windowed[index]
            sample_b = windowed[index + lag]
            numerator += sample_a * sample_b
            energy_a += sample_a * sample_a
            energy_b += sample_b * sample_b
        if energy_a <= 0.0 or energy_b <= 0.0:
            continue
        correlation = numerator / math.sqrt(energy_a * energy_b)
        if correlation > best_corr:
            best_corr = correlation
            best_lag = lag

    if best_corr < min_correlation or best_lag <= 0:
        return None
    return sample_rate / best_lag


def estimate_pitch_contour(
    samples: list[float],
    sample_rate: int,
    *,
    frame_ms: float = 40.0,
    hop_ms: float = 10.0,
) -> list[float | None]:
    frame_size = max(8, int(sample_rate * frame_ms / 1000.0))
    hop_size = max(1, int(sample_rate * hop_ms / 1000.0))

    contour: list[float | None] = []
    for start in range(0, max(0, len(samples) - frame_size), hop_size):
        frame = samples[start : start + frame_size]
        contour.append(estimate_pitch_hz(frame, sample_rate))
    return contour


def _moving_average(values: list[float], radius: int = 1) -> list[float]:
    smoothed: list[float] = []
    for index in range(len(values)):
        start = max(0, index - radius)
        end = min(len(values), index + radius + 1)
        window = values[start:end]
        smoothed.append(sum(window) / len(window))
    return smoothed


def second_syllable_terminal_delta_hz_from_f0(contour: list[float | None]) -> float:
    voiced = [value for value in contour if value is not None]
    if len(voiced) < 12:
        raise ToneModelError("not enough voiced frames for contour analysis")

    second_syllable = voiced[len(voiced) // 2 :]
    if len(second_syllable) < 6:
        second_syllable = voiced

    smoothed = _moving_average(second_syllable, radius=1)
    section = max(1, len(smoothed) // 3)
    start_mean = sum(smoothed[:section]) / section
    end_mean = sum(smoothed[-section:]) / section
    return end_mean - start_mean


def second_syllable_terminal_delta_hz(
    audio_bytes: bytes,
    *,
    audio_format: str = "mp3",
) -> float:
    samples, sample_rate = decode_audio_to_mono_samples(
        audio_bytes,
        audio_format=audio_format,
    )
    contour = estimate_pitch_contour(samples, sample_rate)
    return second_syllable_terminal_delta_hz_from_f0(contour)


def classify_second_syllable_tone_3_or_4_from_delta(delta_hz: float) -> int:
    return 3 if delta_hz >= 0.0 else 4


def classify_second_syllable_tone_3_or_4(
    audio_bytes: bytes,
    *,
    audio_format: str = "mp3",
) -> int:
    delta_hz = second_syllable_terminal_delta_hz(
        audio_bytes,
        audio_format=audio_format,
    )
    return classify_second_syllable_tone_3_or_4_from_delta(delta_hz)
