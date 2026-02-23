from __future__ import annotations

import math

import pytest

from italki_anki.tone_model import (
    ToneModelError,
    classify_second_syllable_tone_3_or_4_from_delta,
    estimate_pitch_hz,
    second_syllable_terminal_delta_hz_from_f0,
)


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
