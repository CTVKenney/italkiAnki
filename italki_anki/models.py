from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence


class ItemType(str, Enum):
    VOCAB = "vocabulary"
    GRAMMAR = "grammar"
    SENTENCE = "sentence"


@dataclass(frozen=True)
class RawLine:
    text: str
    gloss: Optional[str] = None


@dataclass(frozen=True)
class ClassifiedItem:
    item_type: ItemType
    simplified: str
    traditional: str
    pinyin: str
    english: str
    gloss: Optional[str] = None
    measure_word: Optional[str] = None
    measure_word_pinyin: Optional[str] = None


@dataclass(frozen=True)
class VocabCard:
    english: str
    pinyin: str
    simplified: str
    traditional: str
    audio: str


@dataclass(frozen=True)
class ClozeNote:
    text: str


@dataclass(frozen=True)
class ClozeLines:
    english: str
    simplified_chunks: Sequence[str]
    traditional_chunks: Sequence[str]
    pinyin_chunks: Sequence[str]
