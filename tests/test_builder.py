import csv
import re

from italki_anki.audio import NullAudioProvider
from italki_anki.builder import build_from_text
from italki_anki.cards import BuildConfig
from italki_anki.llm import StubClient


def test_stub_grammar_builds_two_cloze_notes(tmp_path):
    output_dir = tmp_path / "out"
    build_from_text(
        "清楚 = 明白",
        StubClient(),
        NullAudioProvider(output_dir=str(output_dir)),
        str(output_dir),
        BuildConfig(),
    )

    with open(output_dir / "cloze_cards.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert len(rows) == 3
    notes = [row[0] for row in rows[1:]]
    assert all("清楚 = 明白" not in note for note in notes)
    assert all("\n" in note for note in notes)
    assert all(len(row) == 1 for row in rows[1:])


def test_stub_sentence_omits_empty_pinyin_line(tmp_path):
    output_dir = tmp_path / "out"
    build_from_text(
        "你可以帮我保留这个座位吗？",
        StubClient(),
        NullAudioProvider(output_dir=str(output_dir)),
        str(output_dir),
        BuildConfig(),
    )

    with open(output_dir / "cloze_cards.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    cloze_text = rows[1][0]
    non_empty_lines = [line for line in cloze_text.splitlines() if line.strip()]
    assert len(non_empty_lines) == 2
    empty_cloze_pattern = re.compile(r"^\{\{c\d+::\}\}$")
    assert all(not empty_cloze_pattern.match(line.strip()) for line in non_empty_lines)


def test_social_chatter_sentence_is_filtered_before_classification(tmp_path):
    output_dir = tmp_path / "out"
    result = build_from_text(
        "感谢老师！下次见\nThank you, teacher! See you next time.\n",
        StubClient(),
        NullAudioProvider(output_dir=str(output_dir)),
        str(output_dir),
        BuildConfig(),
    )
    assert result.vocab_count == 0
    assert result.cloze_count == 0
    assert not (output_dir / "vocab_cards.csv").exists()
    assert not (output_dir / "cloze_cards.csv").exists()


def test_build_from_text_reports_progress_messages(tmp_path):
    output_dir = tmp_path / "out"
    updates: list[str] = []
    build_from_text(
        "书房\nstudy\n",
        StubClient(),
        NullAudioProvider(output_dir=str(output_dir)),
        str(output_dir),
        BuildConfig(),
        status=updates.append,
    )
    assert updates[0] == "Parsing input text"
    assert "Found 1 candidate Chinese lines" in updates
    assert "Classifying candidate lines" in updates
    assert "Writing CSV output files" in updates
    assert updates[-1].startswith("Finished: ")


def test_basic_greeting_lines_are_filtered_before_classification(tmp_path):
    output_dir = tmp_path / "out"
    result = build_from_text(
        "你好\nhello\n",
        StubClient(),
        NullAudioProvider(output_dir=str(output_dir)),
        str(output_dir),
        BuildConfig(),
    )
    assert result.vocab_count == 0
    assert result.cloze_count == 0
    assert not (output_dir / "vocab_cards.csv").exists()
    assert not (output_dir / "cloze_cards.csv").exists()
