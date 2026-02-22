from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

from italki_anki.cli import main, read_text_from_editor
from italki_anki.known_terms import normalize_known_term


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


def test_default_run_mode_writes_latest_and_archive(monkeypatch, tmp_path):
    monkeypatch.setattr("italki_anki.cli.read_text_from_editor", lambda initial_text="": "书房\nstudy\n")
    output_dir = tmp_path / "out"

    exit_code = main(["--interactive", "--out-dir", str(output_dir)])

    assert exit_code == 0
    assert (output_dir / "vocab_cards.csv").exists()
    manifest = json.loads((output_dir / "latest_run.json").read_text(encoding="utf-8"))
    assert manifest["run_mode"] == "both"
    assert manifest["published_latest"] is True
    run_dir = output_dir / "runs" / manifest["run_id"]
    assert (run_dir / "vocab_cards.csv").exists()
    assert (run_dir / "cloze_cards.csv").exists()


def test_run_mode_latest_writes_only_root_files(monkeypatch, tmp_path):
    monkeypatch.setattr("italki_anki.cli.read_text_from_editor", lambda initial_text="": "书房\nstudy\n")
    output_dir = tmp_path / "out"

    exit_code = main(["--interactive", "--out-dir", str(output_dir), "--run-mode", "latest"])

    assert exit_code == 0
    assert (output_dir / "vocab_cards.csv").exists()
    assert not (output_dir / "runs").exists()
    manifest = json.loads((output_dir / "latest_run.json").read_text(encoding="utf-8"))
    assert manifest["run_mode"] == "latest"
    assert manifest["published_latest"] is True


def test_run_mode_archive_writes_only_run_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("italki_anki.cli.read_text_from_editor", lambda initial_text="": "书房\nstudy\n")
    output_dir = tmp_path / "out"

    exit_code = main(["--interactive", "--out-dir", str(output_dir), "--run-mode", "archive"])

    assert exit_code == 0
    assert not (output_dir / "vocab_cards.csv").exists()
    manifest = json.loads((output_dir / "latest_run.json").read_text(encoding="utf-8"))
    assert manifest["run_mode"] == "archive"
    assert manifest["published_latest"] is False
    run_dir = output_dir / "runs" / manifest["run_id"]
    assert (run_dir / "vocab_cards.csv").exists()
    assert (run_dir / "cloze_cards.csv").exists()


def test_cli_emits_stub_classifier_warning_when_openai_disabled(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("italki_anki.cli.read_text_from_editor", lambda initial_text="": "书房\nstudy\n")
    output_dir = tmp_path / "out"

    exit_code = main(["--interactive", "--out-dir", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Classifier: stub heuristic" in captured.err


def test_cli_applies_loaded_known_terms(monkeypatch, tmp_path):
    monkeypatch.setattr("italki_anki.cli.read_text_from_editor", lambda initial_text="": "书房\nstudy\n合同\n")
    monkeypatch.setattr(
        "italki_anki.cli.load_known_terms",
        lambda: {normalize_known_term("书房")},
    )
    output_dir = tmp_path / "out"

    exit_code = main(["--interactive", "--out-dir", str(output_dir)])

    assert exit_code == 0
    with open(output_dir / "vocab_cards.csv", newline="", encoding="utf-8") as handle:
        vocab_rows = list(csv.reader(handle))
    assert [row[2] for row in vocab_rows[1:]] == ["合同"]
