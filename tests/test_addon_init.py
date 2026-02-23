from __future__ import annotations

import importlib
import json
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace


def load_addon_with_fake_aqt(
    monkeypatch,
    *,
    config: dict,
    media_dir: Path,
    has_collection: bool = True,
    notes_rows: list[tuple[int, int, str]] | None = None,
    model_fields_by_mid: dict[int, list[str]] | None = None,
):
    info_messages: list[str] = []
    warning_messages: list[str] = []
    status_messages: list[str] = []
    imported_paths: list[str] = []
    registered_actions: list[object] = []
    deleted_note_ids: list[int] = []
    notes_data: list[tuple[int, int, str]] = list(notes_rows or [])

    class FakeSignal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

    class FakeAction:
        def __init__(self, text, mw):
            self.text = text
            self.mw = mw
            self.triggered = FakeSignal()

    class FakeMenuTools:
        def addAction(self, action):
            registered_actions.append(action)

    class FakeMedia:
        def dir(self):
            return str(media_dir)

    class FakeDB:
        def all(self, query):
            normalized = query.lower()
            if "where id in" in normalized:
                match = re.search(r"where id in\s*\(([^)]*)\)", normalized)
                if match is None:
                    return []
                raw_ids = [part.strip() for part in match.group(1).split(",") if part.strip()]
                ids = {int(part) for part in raw_ids}
                return [row for row in notes_data if int(row[0]) in ids]
            return list(notes_data)

    class FakeModels:
        def get(self, mid):
            field_names = (model_fields_by_mid or {}).get(int(mid))
            if field_names is None:
                return None
            return {"flds": [{"name": name} for name in field_names]}

    class FakeCollection:
        def __init__(self):
            self.media = FakeMedia()
            self.db = FakeDB()
            self.models = FakeModels()

        def remove_notes(self, note_ids):
            deleted_note_ids.extend(note_ids)
            removed = {int(note_id) for note_id in note_ids}
            remaining = [row for row in notes_data if int(row[0]) not in removed]
            notes_data[:] = remaining

    fake_col = FakeCollection() if has_collection else None
    fake_mw = SimpleNamespace(
        col=fake_col,
        addonManager=SimpleNamespace(getConfig=lambda _name: config),
        form=SimpleNamespace(menuTools=FakeMenuTools()),
    )

    fake_aqt = ModuleType("aqt")
    fake_aqt.__path__ = []  # mark as package for `import aqt.submodule`
    fake_aqt.mw = fake_mw

    fake_aqt_utils = ModuleType("aqt.utils")
    fake_aqt_utils.showInfo = lambda message: info_messages.append(message)
    fake_aqt_utils.showWarning = lambda message: warning_messages.append(message)
    fake_aqt_utils.tooltip = lambda message: status_messages.append(message)

    fake_aqt_importing = ModuleType("aqt.importing")
    fake_aqt_importing.import_file = lambda _mw, path: imported_paths.append(path)

    fake_aqt_qt = ModuleType("aqt.qt")
    fake_aqt_qt.QAction = FakeAction

    fake_aqt.utils = fake_aqt_utils
    fake_aqt.importing = fake_aqt_importing
    fake_aqt.qt = fake_aqt_qt

    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)
    monkeypatch.setitem(sys.modules, "aqt.utils", fake_aqt_utils)
    monkeypatch.setitem(sys.modules, "aqt.importing", fake_aqt_importing)
    monkeypatch.setitem(sys.modules, "aqt.qt", fake_aqt_qt)

    module = importlib.import_module("anki_addon.italki_latest_importer")
    module = importlib.reload(module)
    return (
        module,
        info_messages,
        warning_messages,
        status_messages,
        imported_paths,
        registered_actions,
        deleted_note_ids,
        fake_mw,
    )


def test_addon_registers_menu_action(monkeypatch, tmp_path):
    _, _info, _warn, _status, _imports, actions, _deleted, _mw = load_addon_with_fake_aqt(
        monkeypatch,
        config={"output_dir": str(tmp_path / "output")},
        media_dir=tmp_path / "media",
        has_collection=True,
    )
    assert actions
    assert actions[0].text == "Import Latest italki Cards"


def test_addon_imports_existing_csv_and_copies_audio(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    media_dir = tmp_path / "media"
    audio_dir = output_dir / "audio"
    output_dir.mkdir(parents=True)
    media_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)
    (output_dir / "vocab_cards.csv").write_text(
        "English,Pinyin,Simplified,Traditional,Audio\nbook,shū,书,書,[sound:book.mp3]\n",
        encoding="utf-8",
    )
    (output_dir / "cloze_cards.csv").write_text(
        "Text\n{{c1::你好}}，{{c2::老师}}\n",
        encoding="utf-8",
    )
    (audio_dir / "demo.mp3").write_bytes(b"audio")

    module, info_messages, warning_messages, status_messages, imported_paths, _actions, deleted_ids, _mw = load_addon_with_fake_aqt(
        monkeypatch,
        config={"output_dir": str(output_dir)},
        media_dir=media_dir,
        has_collection=True,
    )

    module._import_latest_cards()

    assert not warning_messages
    assert len(imported_paths) == 2
    vocab_import_path = output_dir / ".vocab_cards.anki_import.csv"
    cloze_import_path = output_dir / ".cloze_cards.anki_import.csv"
    assert imported_paths == [str(vocab_import_path), str(cloze_import_path)]
    assert vocab_import_path.read_text(encoding="utf-8").startswith("book,shū,书,書")
    assert "{{c1::你好}}，{{c2::老师}}" in cloze_import_path.read_text(encoding="utf-8")
    assert status_messages == [
        "Import 1/2: vocab cards (vocab_cards.csv) [add-only]",
        "Import 2/2: cloze cards (cloze_cards.csv) [add-only]",
    ]
    assert (media_dir / "demo.mp3").exists()
    assert info_messages and "Started import for 2 file(s)." in info_messages[-1]
    assert "Import mode: add-only." in info_messages[-1]
    assert "Import order: vocab (vocab_cards.csv), cloze (cloze_cards.csv)." in info_messages[-1]
    assert not deleted_ids
    history_path = output_dir / ".anki_import_history.jsonl"
    assert history_path.exists()
    history_lines = history_path.read_text(encoding="utf-8").splitlines()
    assert history_lines
    assert '"imported_files": 2' in history_lines[-1]


def test_addon_add_only_mode_skips_existing_vocab(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    media_dir = tmp_path / "media"
    output_dir.mkdir(parents=True)
    media_dir.mkdir(parents=True)
    (output_dir / "vocab_cards.csv").write_text(
        "English,Pinyin,Simplified,Traditional,Audio\nlong holiday,cháng jià,长假,長假,[sound:a.mp3]\n",
        encoding="utf-8",
    )

    module, info_messages, warning_messages, _status_messages, imported_paths, _actions, deleted_ids, _mw = load_addon_with_fake_aqt(
        monkeypatch,
        config={"output_dir": str(output_dir), "import_cloze": False, "import_mode": "add-only"},
        media_dir=media_dir,
        has_collection=True,
        notes_rows=[(101, 1, "book\x1fshū\x1f长假\x1f長假\x1f[sound:old.mp3]")],
        model_fields_by_mid={1: ["English", "Pinyin", "Simplified", "Traditional", "Audio"]},
    )

    module._import_latest_cards()

    assert not warning_messages
    assert imported_paths == []
    assert deleted_ids == []
    assert "Skipped 1 row(s) already present in collection." in info_messages[-1]


def test_addon_overwrite_mode_deletes_existing_before_import(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    media_dir = tmp_path / "media"
    output_dir.mkdir(parents=True)
    media_dir.mkdir(parents=True)
    (output_dir / "vocab_cards.csv").write_text(
        "English,Pinyin,Simplified,Traditional,Audio\nlong holiday,cháng jià,长假,長假,[sound:a.mp3]\n",
        encoding="utf-8",
    )
    (output_dir / ".anki_managed_notes.json").write_text(
        json.dumps({"vocab": {"长假": [201, 202]}, "cloze": {}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    module, info_messages, warning_messages, _status_messages, imported_paths, _actions, deleted_ids, _mw = load_addon_with_fake_aqt(
        monkeypatch,
        config={"output_dir": str(output_dir), "import_cloze": False, "import_mode": "overwrite"},
        media_dir=media_dir,
        has_collection=True,
        notes_rows=[
            (201, 1, "book\x1fshū\x1f长假\x1f長假\x1f[sound:old1.mp3]"),
            (202, 1, "book\x1fshū\x1f长假\x1f長假\x1f[sound:old2.mp3]"),
        ],
        model_fields_by_mid={1: ["English", "Pinyin", "Simplified", "Traditional", "Audio"]},
    )

    module._import_latest_cards()

    assert not warning_messages
    assert len(imported_paths) == 1
    assert sorted(deleted_ids) == [201, 202]
    assert "Deleted 2 existing note(s) before overwrite import." in info_messages[-1]
    assert "Overwrite scope: tracked-only." in info_messages[-1]
    deleted_file = output_dir / ".anki_deleted_keys.json"
    if deleted_file.exists():
        payload = json.loads(deleted_file.read_text(encoding="utf-8"))
        assert "长假" not in set(payload.get("vocab", []))


def test_addon_overwrite_mode_protects_unmanaged_existing_notes(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    media_dir = tmp_path / "media"
    output_dir.mkdir(parents=True)
    media_dir.mkdir(parents=True)
    (output_dir / "vocab_cards.csv").write_text(
        "English,Pinyin,Simplified,Traditional,Audio\nlong holiday,cháng jià,长假,長假,[sound:a.mp3]\n",
        encoding="utf-8",
    )

    module, info_messages, warning_messages, _status_messages, imported_paths, _actions, deleted_ids, _mw = load_addon_with_fake_aqt(
        monkeypatch,
        config={"output_dir": str(output_dir), "import_cloze": False, "import_mode": "overwrite"},
        media_dir=media_dir,
        has_collection=True,
        notes_rows=[(210, 1, "book\x1fshū\x1f长假\x1f長假\x1f[sound:old.mp3]")],
        model_fields_by_mid={1: ["English", "Pinyin", "Simplified", "Traditional", "Audio"]},
    )

    module._import_latest_cards()

    assert not warning_messages
    assert imported_paths == []
    assert deleted_ids == []
    assert "Protected 1 row(s): matching notes were not managed by this add-on." in info_messages[-1]


def test_manual_deletion_is_tombstoned_and_skipped_later(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    media_dir = tmp_path / "media"
    output_dir.mkdir(parents=True)
    media_dir.mkdir(parents=True)
    (output_dir / "vocab_cards.csv").write_text(
        "English,Pinyin,Simplified,Traditional,Audio\nlong holiday,cháng jià,长假,長假,[sound:a.mp3]\n",
        encoding="utf-8",
    )

    module, info_messages, warning_messages, _status_messages, imported_paths, _actions, deleted_ids, mw = load_addon_with_fake_aqt(
        monkeypatch,
        config={"output_dir": str(output_dir), "import_cloze": False, "import_mode": "add-only"},
        media_dir=media_dir,
        has_collection=True,
        notes_rows=[(301, 1, "book\x1fshū\x1f长假\x1f長假\x1f[sound:old.mp3]")],
        model_fields_by_mid={1: ["English", "Pinyin", "Simplified", "Traditional", "Audio"]},
    )

    module._import_latest_cards()
    assert imported_paths == []
    assert "Skipped 1 row(s) already present in collection." in info_messages[-1]

    # Simulate user deleting the note directly in Anki.
    mw.col.remove_notes([301])

    module._import_latest_cards()

    assert not warning_messages
    assert imported_paths == []
    assert 301 in deleted_ids
    assert "Skipped 1 row(s) previously deleted in Anki." in info_messages[-1]
