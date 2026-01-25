from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .audio import AudioProvider, NullAudioProvider, PollyAudioProvider
from .cards import BuildConfig, build_cloze_notes, build_vocab_cards, write_cloze_csv, write_vocab_csv
from .llm import LLMClient
from .models import ClassifiedItem
from .parser import parse_lines


@dataclass
class BuildResult:
    vocab_count: int
    cloze_count: int


def build_from_text(
    text: str,
    llm: LLMClient,
    audio: AudioProvider,
    output_dir: str,
    config: BuildConfig,
) -> BuildResult:
    raw_lines = parse_lines(text.splitlines())
    if not raw_lines:
        return BuildResult(vocab_count=0, cloze_count=0)
    classified = classify_lines(raw_lines, llm, config)
    vocab_cards = build_vocab_cards(classified, audio, config)
    cloze_notes = build_cloze_notes(classified, config)
    write_vocab_csv(vocab_cards, f"{output_dir}/vocab_cards.csv")
    write_cloze_csv(cloze_notes, f"{output_dir}/cloze_cards.csv")
    return BuildResult(vocab_count=len(vocab_cards), cloze_count=len(cloze_notes))


def classify_lines(
    raw_lines: List,
    llm: LLMClient,
    config: BuildConfig,
) -> List[ClassifiedItem]:
    lines = []
    for line in raw_lines:
        if getattr(line, "gloss", None):
            lines.append(f"{line.text} ({line.gloss})")
        else:
            lines.append(line.text)
    items = llm.classify(lines, seed=config.seed)
    return dedupe_items(items)


def dedupe_items(items: List[ClassifiedItem]) -> List[ClassifiedItem]:
    seen = set()
    deduped = []
    for item in items:
        key = item.simplified.strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def pick_audio_provider(output_dir: str, include_audio: bool) -> AudioProvider:
    if include_audio:
        return PollyAudioProvider(output_dir=output_dir)
    return NullAudioProvider(output_dir=output_dir)
