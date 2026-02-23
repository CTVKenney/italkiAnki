from __future__ import annotations

from pathlib import Path

from anki_addon.italki_latest_importer.shared import (
    AddonConfig,
    append_deleted_keys,
    copy_audio_files,
    dedupe_import_rows,
    existing_key_index,
    filter_rows_by_import_mode,
    filter_rows_by_deleted_keys,
    keys_for_note_ids,
    load_deleted_keys,
    normalize_import_mode,
    planned_import_targets,
    prepare_import_csv,
    resolve_output_paths,
    save_deleted_keys,
    split_existing_targets,
)


def test_addon_config_defaults():
    config = AddonConfig.from_dict(None)
    assert config.output_dir.endswith("Chinese/output")
    assert config.vocab_filename == "vocab_cards.csv"
    assert config.copy_audio is True
    assert config.import_mode == "add-only"


def test_normalize_import_mode():
    assert normalize_import_mode("overwrite") == "overwrite"
    assert normalize_import_mode("add-only") == "add-only"
    assert normalize_import_mode("unknown") == "add-only"


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


def test_dedupe_import_rows_prefers_richer_vocab_row():
    rows = [
        ["", "", "长假", "長假", ""],
        ["long holiday", "cháng jià", "长假", "長假", "[sound:a.mp3]"],
    ]

    deduped, removed = dedupe_import_rows("vocab", rows)

    assert removed == 1
    assert len(deduped) == 1
    assert deduped[0][1] == "cháng jià"


def test_existing_key_index_reads_notes_table():
    class FakeDB:
        def all(self, _query):
            return [
                (1, 1001, "book\x1fshū\x1f长假\x1f長假\x1f[sound:a.mp3]"),
                (2, 1001, "book\x1fshū\x1f长假\x1f長假\x1f[sound:a.mp3]"),
                (3, 1002, "{{c1::你好}}"),
            ]

    class FakeModels:
        def get(self, mid):
            if str(mid) == "1001":
                return {"flds": [{"name": "English"}, {"name": "Pinyin"}, {"name": "Simplified"}]}
            if str(mid) == "1002":
                return {"flds": [{"name": "Text"}]}
            return None

    collection = type("FakeCollection", (), {"db": FakeDB(), "models": FakeModels()})()

    vocab_index = existing_key_index(collection, "vocab")
    cloze_index = existing_key_index(collection, "cloze")

    assert vocab_index["长假"] == [1, 2]
    assert cloze_index["{{c1::你好}}"] == [3]


def test_filter_rows_by_import_mode_add_only_skips_existing():
    rows = [["long holiday", "cháng jià", "长假", "長假", ""]]
    filtered, skipped, note_ids = filter_rows_by_import_mode(
        label="vocab",
        rows=rows,
        mode="add-only",
        key_index={"长假": [11, 12]},
    )
    assert filtered == []
    assert skipped == 1
    assert note_ids == []


def test_filter_rows_by_import_mode_overwrite_collects_note_ids():
    rows = [["long holiday", "cháng jià", "长假", "長假", ""]]
    filtered, skipped, note_ids = filter_rows_by_import_mode(
        label="vocab",
        rows=rows,
        mode="overwrite",
        key_index={"长假": [11, 12]},
    )
    assert filtered == rows
    assert skipped == 0
    assert note_ids == [11, 12]


def test_deleted_keys_roundtrip(tmp_path):
    save_deleted_keys(
        tmp_path,
        {"vocab": {"长假"}, "cloze": {"{{c1::你好}}"}},
    )

    loaded = load_deleted_keys(tmp_path)

    assert loaded["vocab"] == {"长假"}
    assert loaded["cloze"] == {"{{c1::你好}}"}


def test_append_deleted_keys_merges_and_dedupes(tmp_path):
    added_first = append_deleted_keys(tmp_path, {"vocab": {"长假"}, "cloze": set()})
    added_second = append_deleted_keys(tmp_path, {"vocab": {"长假", "复习"}, "cloze": {"{{c1::你好}}"}})

    loaded = load_deleted_keys(tmp_path)

    assert added_first == 1
    assert added_second == 2
    assert loaded["vocab"] == {"长假", "复习"}
    assert loaded["cloze"] == {"{{c1::你好}}"}


def test_filter_rows_by_deleted_keys():
    rows = [["long holiday", "cháng jià", "长假", "長假", ""]]
    kept, skipped = filter_rows_by_deleted_keys(
        label="vocab",
        rows=rows,
        deleted_keys={"长假"},
    )
    assert kept == []
    assert skipped == 1


def test_keys_for_note_ids_reads_field_keys():
    class FakeDB:
        def __init__(self):
            self.rows = [
                (1, 1001, "book\x1fshū\x1f长假\x1f長假\x1f[sound:a.mp3]"),
                (2, 1002, "{{c1::你好}}"),
            ]

        def all(self, query):
            if "where id in (1,2)" in query:
                return list(self.rows)
            return []

    class FakeModels:
        def get(self, mid):
            if str(mid) == "1001":
                return {"flds": [{"name": "English"}, {"name": "Pinyin"}, {"name": "Simplified"}]}
            if str(mid) == "1002":
                return {"flds": [{"name": "Text"}]}
            return None

    collection = type("FakeCollection", (), {"db": FakeDB(), "models": FakeModels()})()

    keys = keys_for_note_ids(collection, [1, 2])

    assert keys["vocab"] == {"长假"}
    assert keys["cloze"] == {"{{c1::你好}}"}
