from __future__ import annotations

import csv
import os
import random
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from .audio import AudioProvider
from .cloze import PINYIN_NUMBERS, build_cloze_lines, render_cloze_lines
from .models import ClassifiedItem, ClozeNote, ItemType, VocabCard

DEGREE_PREFIXES = ("太",)


@dataclass
class BuildConfig:
    max_cloze_len: int = 8
    seed: Optional[int] = None
    include_audio: bool = True


def strip_degree_prefix(text: str) -> str:
    for prefix in DEGREE_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def apply_measure_word(
    simplified: str,
    traditional: str,
    pinyin: str,
    measure_word: Optional[str],
    measure_word_pinyin: Optional[str],
    rng: random.Random,
) -> tuple[str, str, str]:
    if not measure_word:
        return simplified, traditional, pinyin

    if measure_word == "个":
        return simplified, traditional, pinyin

    number = rng.randint(1, 10)
    number_pinyin = PINYIN_NUMBERS.get(number, str(number))
    prefix_simplified = f"{number}{measure_word}"
    prefix_traditional = f"{number}{measure_word}"
    prefix_pinyin = f"{number_pinyin} {measure_word_pinyin or measure_word}"
    return (
        f"{prefix_simplified}{simplified}",
        f"{prefix_traditional}{traditional}",
        f"{prefix_pinyin} {pinyin}",
    )


def build_vocab_cards(
    items: Sequence[ClassifiedItem],
    audio: AudioProvider,
    config: BuildConfig,
) -> List[VocabCard]:
    rng = random.Random(config.seed)
    cards: List[VocabCard] = []
    for item in items:
        if item.item_type is not ItemType.VOCAB:
            continue
        simplified = strip_degree_prefix(item.simplified)
        traditional = strip_degree_prefix(item.traditional)
        pinyin = strip_degree_prefix(item.pinyin)
        simplified, traditional, pinyin = apply_measure_word(
            simplified,
            traditional,
            pinyin,
            item.measure_word,
            item.measure_word_pinyin,
            rng,
        )
        audio_tag = ""
        if config.include_audio:
            filename = audio.create_audio(simplified)
            audio_tag = f"[sound:{filename}]"
        cards.append(
            VocabCard(
                english=item.english,
                pinyin=pinyin,
                simplified=simplified,
                traditional=traditional,
                audio=audio_tag,
            )
        )
    return cards


def build_cloze_notes(
    items: Sequence[ClassifiedItem],
    config: BuildConfig,
) -> List[ClozeNote]:
    notes: List[ClozeNote] = []
    for item in items:
        if item.item_type is ItemType.VOCAB:
            continue
        cloze_lines = build_cloze_lines(
            item.english,
            item.simplified,
            item.traditional,
            item.pinyin,
            config.max_cloze_len,
        )
        rendered_lines = render_cloze_lines(cloze_lines)
        notes.append(ClozeNote(text="\n".join(rendered_lines)))
    return notes


def write_vocab_csv(cards: Iterable[VocabCard], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["English", "Pinyin", "Simplified", "Traditional", "Audio"])
        for card in cards:
            writer.writerow(
                [card.english, card.pinyin, card.simplified, card.traditional, card.audio]
            )


def write_cloze_csv(notes: Iterable[ClozeNote], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Text"])
        for note in notes:
            writer.writerow([note.text])
