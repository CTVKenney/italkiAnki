from __future__ import annotations

import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


def load_addon_with_fake_aqt(
    monkeypatch,
    *,
    config: dict,
    media_dir: Path,
    has_collection: bool = True,
):
    info_messages: list[str] = []
    warning_messages: list[str] = []
    imported_paths: list[str] = []
    registered_actions: list[object] = []

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

    fake_col = SimpleNamespace(media=FakeMedia()) if has_collection else None
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
    return module, info_messages, warning_messages, imported_paths, registered_actions


def test_addon_registers_menu_action(monkeypatch, tmp_path):
    _, _info, _warn, _imports, actions = load_addon_with_fake_aqt(
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
    (output_dir / "vocab_cards.csv").write_text("English,Pinyin,Simplified,Traditional,Audio\n", encoding="utf-8")
    (output_dir / "cloze_cards.csv").write_text("Text\n", encoding="utf-8")
    (audio_dir / "demo.mp3").write_bytes(b"audio")

    module, info_messages, warning_messages, imported_paths, _actions = load_addon_with_fake_aqt(
        monkeypatch,
        config={"output_dir": str(output_dir)},
        media_dir=media_dir,
        has_collection=True,
    )

    module._import_latest_cards()

    assert not warning_messages
    assert len(imported_paths) == 2
    assert str(output_dir / "vocab_cards.csv") in imported_paths
    assert str(output_dir / "cloze_cards.csv") in imported_paths
    assert (media_dir / "demo.mp3").exists()
    assert info_messages and "Started import for 2 file(s)." in info_messages[-1]
