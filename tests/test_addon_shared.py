from __future__ import annotations

from pathlib import Path

from anki_addon.italki_latest_importer.shared import (
    AddonConfig,
    append_import_history,
    append_deleted_keys,
    append_managed_note_ids,
    collect_imported_note_ids_by_key,
    count_cards_for_note_ids,
    copy_audio_files,
    dedupe_import_rows,
    existing_key_index,
    filter_rows_by_import_mode,
    filter_rows_by_deleted_keys,
    keys_for_note_ids,
    load_deleted_keys,
    load_managed_notes,
    normalize_import_mode,
    normalize_overwrite_scope,
    planned_import_targets,
    prepare_import_csv,
    remove_managed_note_ids,
    resolve_output_paths,
    save_deleted_keys,
    save_managed_notes,
    split_existing_targets,
)


def test_addon_config_defaults():
    config = AddonConfig.from_dict(None)
    assert config.output_dir.endswith("Chinese/output")
    assert config.vocab_filename == "vocab_cards.csv"
    assert config.copy_audio is True
    assert config.import_mode == "add-only"
    assert config.overwrite_scope == "tracked-only"


def test_normalize_import_mode():
    assert normalize_import_mode("overwrite") == "overwrite"
    assert normalize_import_mode("add-only") == "add-only"
    assert normalize_import_mode("unknown") == "add-only"


def test_normalize_overwrite_scope():
    assert normalize_overwrite_scope("tracked-only") == "tracked-only"
    assert normalize_overwrite_scope("collection") == "collection"
    assert normalize_overwrite_scope("unknown") == "tracked-only"


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


def test_filter_rows_by_import_mode_overwrite_protects_unmanaged_notes():
    rows = [["long holiday", "cháng jià", "长假", "長假", ""]]
    filtered, skipped, note_ids = filter_rows_by_import_mode(
        label="vocab",
        rows=rows,
        mode="overwrite",
        key_index={"长假": [11, 12]},
        managed_note_ids_by_key={},
    )
    assert filtered == []
    assert skipped == 1
    assert note_ids == []


def test_filter_rows_by_import_mode_overwrite_deletes_only_fully_managed_matches():
    rows = [["long holiday", "cháng jià", "长假", "長假", ""]]
    filtered, skipped, note_ids = filter_rows_by_import_mode(
        label="vocab",
        rows=rows,
        mode="overwrite",
        key_index={"长假": [11, 12]},
        managed_note_ids_by_key={"长假": {11, 12}},
    )
    assert filtered == rows
    assert skipped == 0
    assert sorted(note_ids) == [11, 12]


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


def test_managed_notes_roundtrip(tmp_path):
    save_managed_notes(
        tmp_path,
        {"vocab": {"长假": {11, 12}}, "cloze": {"{{c1::你好}}": {21}}},
    )

    loaded = load_managed_notes(tmp_path)

    assert loaded["vocab"]["长假"] == {11, 12}
    assert loaded["cloze"]["{{c1::你好}}"] == {21}


def test_append_and_remove_managed_note_ids(tmp_path):
    added = append_managed_note_ids(
        tmp_path,
        label="vocab",
        note_ids_by_key={"长假": {11, 12}, "复习": {13}},
    )
    removed = remove_managed_note_ids(tmp_path, [12, 13])
    loaded = load_managed_notes(tmp_path)

    assert added == 3
    assert removed == 2
    assert loaded["vocab"]["长假"] == {11}
    assert "复习" not in loaded["vocab"]


def test_collect_imported_note_ids_by_key():
    rows = [
        ["long holiday", "cháng jià", "长假", "長假", ""],
        ["review", "fùxí", "复习", "複習", ""],
    ]
    imported = collect_imported_note_ids_by_key(
        label="vocab",
        rows=rows,
        key_index_before={"长假": [11], "复习": []},
        key_index_after={"长假": [11, 21], "复习": [31]},
    )
    assert imported == {"长假": {21}, "复习": {31}}


def test_count_cards_for_note_ids_uses_cards_table_count():
    class FakeDB:
        def all(self, query):
            if "from cards where nid in (11,12)" in query:
                return [(3,)]
            return []

    collection = type("FakeCollection", (), {"db": FakeDB()})()
    assert count_cards_for_note_ids(collection, [11, 12]) == 3


def test_append_import_history_writes_jsonl(tmp_path):
    append_import_history(
        tmp_path,
        {
            "import_mode": "add-only",
            "imported_files": 2,
            "estimated_new_cards": 17,
        },
    )

    history_path = tmp_path / ".anki_import_history.jsonl"
    lines = history_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert '"imported_files": 2' in lines[0]
    assert '"estimated_new_cards": 17' in lines[0]
    assert '"timestamp_utc":' in lines[0]


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
