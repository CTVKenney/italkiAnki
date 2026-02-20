from __future__ import annotations

from pathlib import Path

from anki_addon.italki_latest_importer.shared import (
    AddonConfig,
    copy_audio_files,
    planned_import_targets,
    prepare_import_csv,
    resolve_output_paths,
    split_existing_targets,
)


def test_addon_config_defaults():
    config = AddonConfig.from_dict(None)
    assert config.output_dir.endswith("Chinese/output")
    assert config.vocab_filename == "vocab_cards.csv"
    assert config.copy_audio is True


def test_resolve_output_paths_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    config = AddonConfig(output_dir="~/Chinese/output")
    paths = resolve_output_paths(config)
    assert paths.base_dir == tmp_path / "Chinese" / "output"
    assert paths.vocab_csv == paths.base_dir / "vocab_cards.csv"
    assert paths.cloze_csv == paths.base_dir / "cloze_cards.csv"
    assert paths.audio_dir == paths.base_dir / "audio"


def test_planned_import_targets_respects_flags(tmp_path):
    config = AddonConfig(output_dir=str(tmp_path), import_vocab=True, import_cloze=False)
    paths = resolve_output_paths(config)
    targets = planned_import_targets(config, paths)
    assert targets == [("vocab", paths.vocab_csv)]


def test_split_existing_targets(tmp_path):
    existing = tmp_path / "vocab_cards.csv"
    existing.write_text("header\n", encoding="utf-8")
    missing = tmp_path / "cloze_cards.csv"
    targets = [("vocab", existing), ("cloze", missing)]
    found, not_found = split_existing_targets(targets)
    assert found == [("vocab", existing)]
    assert not_found == [("cloze", missing)]


def test_copy_audio_files_copies_new_audio_only(tmp_path):
    audio_dir = tmp_path / "output" / "audio"
    media_dir = tmp_path / "media"
    audio_dir.mkdir(parents=True)
    media_dir.mkdir()
    (audio_dir / "a.mp3").write_bytes(b"a")
    (audio_dir / "b.wav").write_bytes(b"b")
    (audio_dir / "ignore.txt").write_text("x", encoding="utf-8")
    (media_dir / "b.wav").write_bytes(b"old")

    copied = copy_audio_files(audio_dir, media_dir)

    assert copied == 1
    assert (media_dir / "a.mp3").exists()
    assert (media_dir / "b.wav").read_bytes() == b"old"
    assert not (media_dir / "ignore.txt").exists()


def test_prepare_import_csv_strips_known_header_row(tmp_path):
    source = tmp_path / "vocab_cards.csv"
    source.write_text(
        "English,Pinyin,Simplified,Traditional,Audio\nbook,shu,书,書,[sound:a.mp3]\n",
        encoding="utf-8",
    )

    import_path = prepare_import_csv(source)

    assert import_path != source
    assert import_path.name == ".vocab_cards.anki_import.csv"
    assert import_path.read_text(encoding="utf-8").startswith("book,shu,书,書")


def test_prepare_import_csv_keeps_unknown_first_row(tmp_path):
    source = tmp_path / "custom.csv"
    source.write_text("word,reading\nbook,shu\n", encoding="utf-8")

    import_path = prepare_import_csv(source)

    assert import_path == source
