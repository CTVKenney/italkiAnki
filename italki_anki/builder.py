from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Set

from .audio import AudioProvider, NullAudioProvider, PollyAudioProvider
from .cards import BuildConfig, build_cloze_notes, build_vocab_cards, write_cloze_csv, write_vocab_csv
from .llm import LLMClient
from .models import ClassifiedItem, ItemType
from .known_terms import normalize_known_term
from .parser import parse_lines


@dataclass
class BuildResult:
    vocab_count: int
    cloze_count: int


StatusCallback = Callable[[str], None]


def emit_status(status: StatusCallback | None, message: str) -> None:
    if status is not None:
        status(message)


def build_from_text(
    text: str,
    llm: LLMClient,
    audio: AudioProvider,
    output_dir: str,
    config: BuildConfig,
    known_terms: Set[str] | None = None,
    status: StatusCallback | None = None,
) -> BuildResult:
    emit_status(status, "Parsing input text")
    raw_lines = parse_lines(text.splitlines())
    emit_status(status, f"Found {len(raw_lines)} candidate Chinese lines")
    if not raw_lines:
        emit_status(status, "No learnable items found after filtering")
        return BuildResult(vocab_count=0, cloze_count=0)
    emit_status(status, "Classifying candidate lines")
    classified = classify_lines(raw_lines, llm, config)
    classified, known_terms_dropped = filter_known_vocab_items(classified, known_terms or set())
    emit_status(status, f"Classified {len(classified)} unique items")
    if known_terms:
        emit_status(status, f"Dropped {known_terms_dropped} known/basic vocab items")
    emit_status(status, "Building vocab and cloze cards")
    vocab_cards = build_vocab_cards(classified, audio, config)
    cloze_notes = build_cloze_notes(classified, config)
    emit_status(status, "Writing CSV output files")
    write_vocab_csv(vocab_cards, f"{output_dir}/vocab_cards.csv")
    write_cloze_csv(cloze_notes, f"{output_dir}/cloze_cards.csv")
    emit_status(
        status,
        f"Finished: {len(vocab_cards)} vocab cards and {len(cloze_notes)} cloze notes",
    )
    return BuildResult(vocab_count=len(vocab_cards), cloze_count=len(cloze_notes))


def filter_known_vocab_items(
    items: List[ClassifiedItem],
    known_terms: Set[str],
) -> tuple[List[ClassifiedItem], int]:
    if not known_terms:
        return items, 0

    filtered: List[ClassifiedItem] = []
    dropped = 0
    for item in items:
        if item.item_type is not ItemType.VOCAB:
            filtered.append(item)
            continue
        candidate_terms = (
            item.simplified,
            item.traditional,
            item.english,
            item.gloss or "",
        )
        if any(normalize_known_term(candidate) in known_terms for candidate in candidate_terms):
            dropped += 1
            continue
        filtered.append(item)
    return filtered, dropped


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
