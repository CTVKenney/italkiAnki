from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_OUTPUT_DIR = "~/Chinese/output"
DEFAULT_VOCAB_FILENAME = "vocab_cards.csv"
DEFAULT_CLOZE_FILENAME = "cloze_cards.csv"
DEFAULT_AUDIO_SUBDIR = "audio"
AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".ogg")
KNOWN_HEADER_ROWS = {
    ("English", "Pinyin", "Simplified", "Traditional", "Audio"),
    ("Text",),
}


@dataclass(frozen=True)
class AddonConfig:
    output_dir: str = DEFAULT_OUTPUT_DIR
    vocab_filename: str = DEFAULT_VOCAB_FILENAME
    cloze_filename: str = DEFAULT_CLOZE_FILENAME
    audio_subdir: str = DEFAULT_AUDIO_SUBDIR
    import_vocab: bool = True
    import_cloze: bool = True
    copy_audio: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "AddonConfig":
        data = raw or {}
        return cls(
            output_dir=str(data.get("output_dir", DEFAULT_OUTPUT_DIR)),
            vocab_filename=str(data.get("vocab_filename", DEFAULT_VOCAB_FILENAME)),
            cloze_filename=str(data.get("cloze_filename", DEFAULT_CLOZE_FILENAME)),
            audio_subdir=str(data.get("audio_subdir", DEFAULT_AUDIO_SUBDIR)),
            import_vocab=bool(data.get("import_vocab", True)),
            import_cloze=bool(data.get("import_cloze", True)),
            copy_audio=bool(data.get("copy_audio", True)),
        )


@dataclass(frozen=True)
class OutputPaths:
    base_dir: Path
    vocab_csv: Path
    cloze_csv: Path
    audio_dir: Path


def resolve_output_paths(config: AddonConfig) -> OutputPaths:
    base_dir = Path(config.output_dir).expanduser()
    return OutputPaths(
        base_dir=base_dir,
        vocab_csv=base_dir / config.vocab_filename,
        cloze_csv=base_dir / config.cloze_filename,
        audio_dir=base_dir / config.audio_subdir,
    )


def planned_import_targets(config: AddonConfig, paths: OutputPaths) -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = []
    if config.import_vocab:
        targets.append(("vocab", paths.vocab_csv))
    if config.import_cloze:
        targets.append(("cloze", paths.cloze_csv))
    return targets


def split_existing_targets(
    targets: Iterable[tuple[str, Path]],
) -> tuple[list[tuple[str, Path]], list[tuple[str, Path]]]:
    existing: list[tuple[str, Path]] = []
    missing: list[tuple[str, Path]] = []
    for label, path in targets:
        if path.exists():
            existing.append((label, path))
        else:
            missing.append((label, path))
    return existing, missing


def copy_audio_files(audio_dir: Path, media_dir: Path) -> int:
    if not audio_dir.exists() or not audio_dir.is_dir():
        return 0
    media_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for source in sorted(audio_dir.iterdir()):
        if not source.is_file():
            continue
        if source.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        target = media_dir / source.name
        if target.exists():
            continue
        shutil.copy2(source, target)
        copied += 1
    return copied


def prepare_import_csv(path: Path) -> Path:
    if not path.exists() or not path.is_file():
        return path
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        first_row = next(reader, None)
        if first_row is None:
            return path
        normalized_first_row = tuple(cell.strip() for cell in first_row)
        if normalized_first_row not in KNOWN_HEADER_ROWS:
            return path
        import_path = path.with_name(f".{path.stem}.anki_import{path.suffix}")
        with open(import_path, "w", newline="", encoding="utf-8") as import_handle:
            writer = csv.writer(import_handle)
            for row in reader:
                writer.writerow(row)
        return import_path
