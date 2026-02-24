from __future__ import annotations

import math
import statistics

import pytest

from italki_anki.tone_model import (
    ToneModelError,
    classify_second_syllable_tone_3_or_4_from_delta,
    estimate_pitch_contour,
    estimate_pitch_hz,
    second_syllable_terminal_delta_hz_from_f0,
)


def _sine_wave(
    *,
    frequency_hz: float,
    sample_rate: int,
    duration_seconds: float,
) -> list[float]:
    sample_count = int(sample_rate * duration_seconds)
    return [
        math.sin((2.0 * math.pi * frequency_hz * index) / sample_rate)
        for index in range(sample_count)
    ]


def _tone_schedule_contour(
    frequencies_hz: list[float],
    *,
    sample_rate: int = 16_000,
    frame_ms: float = 40.0,
) -> list[float | None]:
    frame_size = int(sample_rate * frame_ms / 1000.0)
    contour: list[float | None] = []
    for frequency_hz in frequencies_hz:
        frame = [
            math.sin((2.0 * math.pi * frequency_hz * index) / sample_rate)
            for index in range(frame_size)
        ]
        contour.append(estimate_pitch_hz(frame, sample_rate))
    return contour


def test_estimate_pitch_hz_detects_simple_sine_wave():
    sample_rate = 16_000
    frequency_hz = 200.0
    frame_size = int(sample_rate * 0.04)
    frame = [
        math.sin((2.0 * math.pi * frequency_hz * index) / sample_rate)
        for index in range(frame_size)
    ]

    detected = estimate_pitch_hz(frame, sample_rate)
    assert detected is not None
    assert detected == pytest.approx(frequency_hz, rel=0.05)


@pytest.mark.parametrize("frequency_hz", [110.0, 180.0, 300.0])
def test_estimate_pitch_hz_detects_multiple_valid_frequencies(frequency_hz: float):
    sample_rate = 16_000
    frame = _sine_wave(
        frequency_hz=frequency_hz,
        sample_rate=sample_rate,
        duration_seconds=0.04,
    )
    detected = estimate_pitch_hz(frame, sample_rate)
    assert detected is not None
    assert detected == pytest.approx(frequency_hz, rel=0.06)


def test_estimate_pitch_hz_returns_none_for_silence():
    sample_rate = 16_000
    frame = [0.0] * int(sample_rate * 0.04)
    assert estimate_pitch_hz(frame, sample_rate) is None


def test_estimate_pitch_contour_tracks_constant_frequency():
    sample_rate = 16_000
    samples = _sine_wave(
        frequency_hz=220.0,
        sample_rate=sample_rate,
        duration_seconds=1.2,
    )
    contour = estimate_pitch_contour(samples, sample_rate)
    voiced = [value for value in contour if value is not None]

    assert len(voiced) >= 60
    assert statistics.median(voiced) == pytest.approx(220.0, rel=0.05)


def test_pitch_estimation_and_delta_classify_tone4_for_falling_second_syllable():
    first_syllable = [180.0] * 12
    second_syllable = [
        260.0,
        250.0,
        240.0,
        230.0,
        220.0,
        210.0,
        200.0,
        190.0,
        180.0,
        170.0,
        160.0,
        150.0,
    ]
    contour = _tone_schedule_contour(first_syllable + second_syllable)

    delta = second_syllable_terminal_delta_hz_from_f0(contour)
    assert classify_second_syllable_tone_3_or_4_from_delta(delta) == 4


def test_pitch_estimation_and_delta_classify_tone3_for_rising_second_syllable():
    first_syllable = [180.0] * 12
    second_syllable = [
        150.0,
        140.0,
        130.0,
        140.0,
        160.0,
        180.0,
        200.0,
        220.0,
        230.0,
        240.0,
        250.0,
        260.0,
    ]
    contour = _tone_schedule_contour(first_syllable + second_syllable)

    delta = second_syllable_terminal_delta_hz_from_f0(contour)
    assert classify_second_syllable_tone_3_or_4_from_delta(delta) == 3


def test_second_syllable_delta_is_negative_for_falling_contour():
    first_syllable = [180.0] * 12
    second_syllable = [260.0, 250.0, 240.0, 230.0, 220.0, 210.0, 200.0, 190.0, 180.0, 170.0, 160.0, 150.0]
    contour = first_syllable + second_syllable

    delta = second_syllable_terminal_delta_hz_from_f0(contour)
    assert delta < 0.0


def test_second_syllable_delta_is_positive_for_dip_then_rise_contour():
    first_syllable = [180.0] * 12
    second_syllable = [150.0, 140.0, 130.0, 140.0, 160.0, 180.0, 200.0, 220.0, 230.0, 240.0, 250.0, 260.0]
    contour = first_syllable + second_syllable

    delta = second_syllable_terminal_delta_hz_from_f0(contour)
    assert delta > 0.0


def test_classify_second_syllable_tone_from_delta():
    assert classify_second_syllable_tone_3_or_4_from_delta(-5.0) == 4
    assert classify_second_syllable_tone_3_or_4_from_delta(0.0) == 3
    assert classify_second_syllable_tone_3_or_4_from_delta(7.5) == 3


def test_second_syllable_delta_raises_with_insufficient_voiced_frames():
    with pytest.raises(ToneModelError):
        second_syllable_terminal_delta_hz_from_f0([None, 100.0, None, 90.0, None])
