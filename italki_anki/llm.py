from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List

from .models import ClassifiedItem, ItemType


@dataclass
class LLMClient:
    def classify(self, lines: Iterable[str], seed: int | None = None) -> List[ClassifiedItem]:
        raise NotImplementedError


def parse_classified_items(payload: str) -> List[ClassifiedItem]:
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("LLM response must be a list")
    items: List[ClassifiedItem] = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("LLM entry must be object")
        item_type = ItemType(entry["item_type"])
        items.append(
            ClassifiedItem(
                item_type=item_type,
                simplified=entry["simplified"],
                traditional=entry["traditional"],
                pinyin=entry["pinyin"],
                english=entry["english"],
                gloss=entry.get("gloss"),
                measure_word=entry.get("measure_word"),
                measure_word_pinyin=entry.get("measure_word_pinyin"),
            )
        )
    return items
