import csv

from italki_anki.audio import NullAudioProvider
from italki_anki.builder import build_from_text
from italki_anki.cards import BuildConfig
from italki_anki.llm import StubClient


def test_cloze_csv_writes_single_row_with_embedded_newline(tmp_path):
    output_dir = tmp_path / "out"
    build_from_text(
        "你好吗？",
        StubClient(),
        NullAudioProvider(output_dir=str(output_dir)),
        str(output_dir),
        BuildConfig(),
    )

    with open(output_dir / "cloze_cards.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert len(rows) == 2
    assert len(rows[1]) == 1
    assert "\n" in rows[1][0]
