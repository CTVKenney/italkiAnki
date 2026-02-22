from __future__ import annotations

from italki_anki.known_terms import load_known_terms, normalize_known_term


def test_normalize_known_term_strips_whitespace_and_punctuation():
    assert normalize_known_term("  没关系！ ") == "没关系"
    assert normalize_known_term("Ni Hao!") == "nihao"


def test_load_known_terms_ignores_comments_and_blank_lines(tmp_path):
    terms_file = tmp_path / "known_terms.txt"
    terms_file.write_text(
        "# comment\n\n大学\n  现在  \nNi Hao!\n",
        encoding="utf-8",
    )

    loaded = load_known_terms(terms_file)

    assert loaded == {"大学", "现在", "nihao"}
