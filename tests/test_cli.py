from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

from italki_anki.cli import main, read_text_from_editor


def test_interactive_mode_builds_csv_output(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "italki_anki.cli.read_text_from_editor",
        lambda initial_text="": "书房\nstudy\n清楚 = 明白\n",
    )
    output_dir = tmp_path / "out"

    exit_code = main(["--interactive", "--out-dir", str(output_dir)])

    assert exit_code == 0
    with open(output_dir / "vocab_cards.csv", newline="", encoding="utf-8") as handle:
        vocab_rows = list(csv.reader(handle))
    with open(output_dir / "cloze_cards.csv", newline="", encoding="utf-8") as handle:
        cloze_rows = list(csv.reader(handle))

    assert vocab_rows[0] == ["English", "Pinyin", "Simplified", "Traditional", "Audio"]
    assert vocab_rows[1][2] == "书房"
    assert vocab_rows[1][4] == ""
    assert len(cloze_rows) == 3


def test_read_text_from_editor_uses_editor_env(monkeypatch):
    captured: dict[str, list[str]] = {}

    def fake_run(command, check=False):
        captured["command"] = command
        temp_path = Path(command[-1])
        temp_path.write_text("书房\n", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("EDITOR", "fake-editor --wait")
    monkeypatch.setattr("subprocess.run", fake_run)

    text = read_text_from_editor()

    assert text == "书房\n"
    assert captured["command"][:2] == ["fake-editor", "--wait"]


def test_legacy_build_arguments_still_work(tmp_path):
    input_path = tmp_path / "lesson.txt"
    input_path.write_text("书房\nstudy\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    exit_code = main(["build", str(input_path), "--out-dir", str(output_dir)])

    assert exit_code == 0
    assert (output_dir / "vocab_cards.csv").exists()


def test_main_handles_runtime_errors_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr("italki_anki.cli.read_text_from_editor", lambda initial_text="": "书房\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(["--interactive", "--openai"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "OPENAI_API_KEY is not set" in captured.err
