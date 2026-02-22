from __future__ import annotations

import builtins
import sys
from types import SimpleNamespace

import pytest

from italki_anki.audio import (
    NullAudioProvider,
    PollyAudioProvider,
    build_polly_phoneme_ssml,
    deterministic_audio_filename,
)


def test_deterministic_audio_filename_is_stable_and_trimmed():
    name_a = deterministic_audio_filename("  书房  ")
    name_b = deterministic_audio_filename("书房")
    assert name_a == name_b
    assert name_a.startswith("audio_")
    assert name_a.endswith(".mp3")


def test_null_audio_provider_returns_empty_tag():
    provider = NullAudioProvider(output_dir=".")
    assert provider.create_audio("书房") == ""


def test_deterministic_audio_filename_includes_pronunciation_hint():
    base = deterministic_audio_filename("长假")
    hinted = deterministic_audio_filename("长假", pronunciation_hint="chángjià")
    assert base != hinted


def test_polly_audio_provider_skips_synthesis_when_file_exists(tmp_path, monkeypatch):
    provider = PollyAudioProvider(output_dir=str(tmp_path))
    filename = deterministic_audio_filename("书房")
    existing = tmp_path / filename
    existing.write_bytes(b"already-here")

    fake_boto3 = SimpleNamespace(client=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not call boto3")))
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    result = provider.create_audio("书房")
    assert result == filename
    assert existing.read_bytes() == b"already-here"


def test_polly_audio_provider_writes_audio_from_mocked_boto3(tmp_path, monkeypatch):
    provider = PollyAudioProvider(output_dir=str(tmp_path))
    synth_calls: list[dict] = []

    class FakeStream:
        def read(self) -> bytes:
            return b"fake-mp3"

    class FakeClient:
        def synthesize_speech(self, **kwargs):
            synth_calls.append(kwargs)
            return {"AudioStream": FakeStream()}

    fake_boto3 = SimpleNamespace(client=lambda service_name: FakeClient() if service_name == "polly" else None)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    filename = provider.create_audio("胡萝卜")
    output_path = tmp_path / filename
    assert output_path.exists()
    assert output_path.read_bytes() == b"fake-mp3"
    assert synth_calls and synth_calls[0]["Text"] == "胡萝卜"
    assert synth_calls[0]["TextType"] == "text"
    assert synth_calls[0]["LanguageCode"] == "cmn-CN"


def test_polly_audio_provider_uses_ssml_phoneme_when_pinyin_present(tmp_path, monkeypatch):
    provider = PollyAudioProvider(output_dir=str(tmp_path))
    synth_calls: list[dict] = []

    class FakeStream:
        def read(self) -> bytes:
            return b"fake-mp3"

    class FakeClient:
        def synthesize_speech(self, **kwargs):
            synth_calls.append(kwargs)
            return {"AudioStream": FakeStream()}

    fake_boto3 = SimpleNamespace(client=lambda service_name: FakeClient() if service_name == "polly" else None)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    filename = provider.create_audio("长假", pinyin="chángjià")
    output_path = tmp_path / filename
    assert output_path.exists()
    assert synth_calls and synth_calls[0]["TextType"] == "ssml"
    assert "x-amazon-pinyin" in synth_calls[0]["Text"]
    assert 'ph="chángjià"' in synth_calls[0]["Text"]


def test_build_polly_phoneme_ssml_escapes_xml():
    ssml = build_polly_phoneme_ssml("甲&乙", "jia3 & yi3")
    assert "甲&amp;乙" in ssml
    assert "jia3 &amp; yi3" in ssml


def test_polly_audio_provider_raises_when_stream_missing(tmp_path, monkeypatch):
    provider = PollyAudioProvider(output_dir=str(tmp_path))

    class FakeClient:
        def synthesize_speech(self, **kwargs):
            del kwargs
            return {}

    fake_boto3 = SimpleNamespace(client=lambda service_name: FakeClient() if service_name == "polly" else None)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    with pytest.raises(RuntimeError, match="Polly did not return audio stream"):
        provider.create_audio("书房")


def test_polly_audio_provider_raises_when_boto3_missing(tmp_path, monkeypatch):
    provider = PollyAudioProvider(output_dir=str(tmp_path))
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "boto3":
            raise ImportError("missing boto3")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setitem(sys.modules, "boto3", None)

    with pytest.raises(RuntimeError, match="boto3 is required for Polly audio"):
        provider.create_audio("书房")
