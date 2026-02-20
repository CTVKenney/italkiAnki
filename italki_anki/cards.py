from __future__ import annotations

import csv
import os
import random
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from .audio import AudioProvider
from .cloze import PINYIN_NUMBERS, build_cloze_lines, render_cloze_lines
from .models import ClassifiedItem, ClozeNote, ItemType, VocabCard

DEGREE_PREFIXES = ("太",)
HANZI_NUMBERS = {
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
    10: "十",
}
ENGLISH_NUMBERS = {
    1: "One",
    2: "Two",
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
}


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
) -> tuple[str, str, str, Optional[int]]:
    if not measure_word:
        return simplified, traditional, pinyin, None
    if measure_word == "个":
        return simplified, traditional, pinyin, None

    number = rng.randint(1, 10)
    number_hanzi = HANZI_NUMBERS.get(number, str(number))
    number_pinyin = PINYIN_NUMBERS.get(number, str(number))
    prefix_simplified = f"{number_hanzi}{measure_word}"
    prefix_traditional = f"{number_hanzi}{measure_word}"
    prefix_pinyin = f"{number_pinyin} {measure_word_pinyin or measure_word}"
    return (
        f"{prefix_simplified}{simplified}",
        f"{prefix_traditional}{traditional}",
        f"{prefix_pinyin} {pinyin}",
        number,
    )


def pluralize_english_word(word: str) -> str:
    lower = word.lower()
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return f"{word}es"
    if lower.endswith("y") and len(word) > 1 and lower[-2] not in "aeiou":
        return f"{word[:-1]}ies"
    return f"{word}s"


def build_counted_english(english: str, number: int) -> str:
    normalized = english.strip()
    if not normalized:
        return normalized
    normalized = re.sub(r"^(a|an)\s+", "", normalized, flags=re.IGNORECASE)
    if " " not in normalized and normalized.isalpha():
        normalized = pluralize_english_word(normalized)
    number_word = ENGLISH_NUMBERS.get(number, str(number))
    return f"{number_word} {normalized}"


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
        simplified, traditional, pinyin, number = apply_measure_word(
            simplified,
            traditional,
            pinyin,
            item.measure_word,
            item.measure_word_pinyin,
            rng,
        )
        english = item.english
        if number is not None:
            english = build_counted_english(english, number)
        audio_tag = ""
        if config.include_audio:
            filename = audio.create_audio(simplified)
            audio_tag = f"[sound:{filename}]"
        cards.append(
            VocabCard(
                english=english,
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
        if item.item_type is ItemType.GRAMMAR and is_stub_grammar_item(item):
            example_sentences = build_stub_grammar_examples(item.simplified)
            for sentence in example_sentences:
                cloze_lines = build_cloze_lines(
                    "",
                    sentence,
                    sentence,
                    "",
                    config.max_cloze_len,
                )
                rendered_lines = render_cloze_lines(cloze_lines)
                notes.append(ClozeNote(text="\n".join(rendered_lines)))
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


def is_stub_grammar_item(item: ClassifiedItem) -> bool:
    return (
        not item.english.strip()
        and not item.pinyin.strip()
        and item.simplified == item.traditional
        and "=" in item.simplified
    )


def build_stub_grammar_examples(text: str) -> List[str]:
    left, _, right = text.partition("=")
    left = left.strip()
    right = right.strip()
    sentences: List[str] = []
    if left:
        sentences.append(f"我说得很{left}。")
    if right:
        sentences.append(f"你{right}了吗？")
    if len(sentences) < 2:
        sentences.append("请再说明一次。")
    return sentences[:2]


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
