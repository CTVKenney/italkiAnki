from __future__ import annotations

import builtins
import json

import pytest

from italki_anki.tone_ai import (
    HFWav2Vec2PinyinToneClassifier,
    ToneAIError,
    ToneEvalSample,
    TonePrediction,
    evaluate_tone_classifier,
    extract_tone_digits,
    load_tone_eval_samples,
    pick_tone_from_transcript,
    write_tone_eval_json,
)


def test_extract_tone_digits_parses_numbered_pinyin_transcripts():
    assert extract_tone_digits("h en3") == [3]
    assert extract_tone_digits("ni3 hao3 ma5") == [3, 3, 5]
    assert extract_tone_digits("ZH ANG4") == [4]


def test_pick_tone_from_transcript_supports_indexing():
    transcript = "ni3 hao3 ma5"
    assert pick_tone_from_transcript(transcript) == 5
    assert pick_tone_from_transcript(transcript, syllable_index=0) == 3


def test_pick_tone_from_transcript_rejects_neutral_when_disabled():
    with pytest.raises(ToneAIError, match="neutral tone"):
        pick_tone_from_transcript("ni3 hao3 ma5", allow_neutral_tone=False)


def test_pick_tone_from_transcript_raises_without_tone_digits():
    with pytest.raises(ToneAIError, match="no tone digits"):
        pick_tone_from_transcript("ni hao ma")


def test_load_tone_eval_samples_parses_relative_paths_and_comments(tmp_path):
    audio_a = tmp_path / "a.mp3"
    audio_b = tmp_path / "b.wav"
    audio_a.write_bytes(b"a")
    audio_b.write_bytes(b"b")

    manifest = tmp_path / "samples.tsv"
    manifest.write_text(
        "# comment\n"
        "a.mp3\t3\n"
        "b.wav\t4\n",
        encoding="utf-8",
    )

    samples = load_tone_eval_samples(manifest)
    assert len(samples) == 2
    assert samples[0].audio_path == audio_a.resolve()
    assert samples[0].expected_tone == 3
    assert samples[0].audio_format == "mp3"
    assert samples[1].audio_format == "wav"


def test_evaluate_tone_classifier_tracks_success_and_failure(tmp_path):
    audio_ok = tmp_path / "ok.mp3"
    audio_fail = tmp_path / "fail.mp3"
    audio_ok.write_bytes(b"ok")
    audio_fail.write_bytes(b"fail")

    samples = [
        ToneEvalSample(audio_path=audio_ok, expected_tone=3, audio_format="mp3"),
        ToneEvalSample(audio_path=audio_fail, expected_tone=4, audio_format="mp3"),
    ]

    class FakeClassifier:
        def classify(self, audio_bytes: bytes, *, audio_format: str = "mp3") -> TonePrediction:
            del audio_format
            if audio_bytes == b"fail":
                raise RuntimeError("decode failed")
            return TonePrediction(tone=3, transcript="hao3")

    summary, records = evaluate_tone_classifier(FakeClassifier(), samples)

    assert summary.total == 2
    assert summary.predicted == 1
    assert summary.correct == 1
    assert summary.accuracy == pytest.approx(1.0)
    assert records[0].correct is True
    assert records[1].predicted_tone is None
    assert records[1].error == "decode failed"


def test_write_tone_eval_json_writes_serialized_summary(tmp_path):
    samples = [ToneEvalSample(audio_path=tmp_path / "a.mp3", expected_tone=1, audio_format="mp3")]

    class FakeClassifier:
        def classify(self, audio_bytes: bytes, *, audio_format: str = "mp3") -> TonePrediction:
            del audio_bytes, audio_format
            return TonePrediction(tone=1, transcript="ma1")

    (tmp_path / "a.mp3").write_bytes(b"a")
    summary, records = evaluate_tone_classifier(FakeClassifier(), samples)
    output = write_tone_eval_json(tmp_path / "result.json", summary, records)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["accuracy"] == pytest.approx(1.0)
    assert payload["records"][0]["predicted_tone"] == 1


def test_hf_classifier_reports_missing_optional_dependencies(monkeypatch):
    classifier = HFWav2Vec2PinyinToneClassifier()
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"torch", "transformers"}:
            raise ImportError(f"missing {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ToneAIError, match="torch and transformers"):
        classifier.classify(b"fake-audio", audio_format="mp3")

