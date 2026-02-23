from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

DEFAULT_OUTPUT_DIR = "~/Chinese/output"
DEFAULT_VOCAB_FILENAME = "vocab_cards.csv"
DEFAULT_CLOZE_FILENAME = "cloze_cards.csv"
DEFAULT_AUDIO_SUBDIR = "audio"
DEFAULT_IMPORT_MODE = "add-only"
ImportMode = Literal["add-only", "overwrite"]
DEFAULT_OVERWRITE_SCOPE = "tracked-only"
OverwriteScope = Literal["tracked-only", "collection"]
AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".ogg")
KNOWN_HEADER_ROWS = {
    ("English", "Pinyin", "Simplified", "Traditional", "Audio"),
    ("Text",),
}
FIELD_SEPARATOR = "\x1f"
VOCAB_FIELD_NAME = "Simplified"
CLOZE_FIELD_NAME = "Text"
DELETED_KEYS_FILENAME = ".anki_deleted_keys.json"
MANAGED_NOTES_FILENAME = ".anki_managed_notes.json"
IMPORT_HISTORY_FILENAME = ".anki_import_history.jsonl"


@dataclass(frozen=True)
class AddonConfig:
    output_dir: str = DEFAULT_OUTPUT_DIR
    vocab_filename: str = DEFAULT_VOCAB_FILENAME
    cloze_filename: str = DEFAULT_CLOZE_FILENAME
    audio_subdir: str = DEFAULT_AUDIO_SUBDIR
    import_vocab: bool = True
    import_cloze: bool = True
    copy_audio: bool = True
    import_mode: ImportMode = DEFAULT_IMPORT_MODE
    overwrite_scope: OverwriteScope = DEFAULT_OVERWRITE_SCOPE

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
            import_mode=normalize_import_mode(data.get("import_mode", DEFAULT_IMPORT_MODE)),
            overwrite_scope=normalize_overwrite_scope(
                data.get("overwrite_scope", DEFAULT_OVERWRITE_SCOPE)
            ),
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
    rows = read_csv_rows(path)
    if not rows:
        return path
    first_row = rows[0]
    normalized_first_row = tuple(cell.strip() for cell in first_row)
    if normalized_first_row not in KNOWN_HEADER_ROWS:
        return path
    return write_import_rows(path, rows[1:])


def normalize_import_mode(raw: Any) -> ImportMode:
    value = str(raw or DEFAULT_IMPORT_MODE).strip().lower()
    if value == "overwrite":
        return "overwrite"
    return "add-only"


def normalize_overwrite_scope(raw: Any) -> OverwriteScope:
    value = str(raw or DEFAULT_OVERWRITE_SCOPE).strip().lower()
    if value == "collection":
        return "collection"
    return "tracked-only"


def read_csv_rows(path: Path) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def write_import_rows(path: Path, rows: Iterable[list[str]]) -> Path:
    import_path = path.with_name(f".{path.stem}.anki_import{path.suffix}")
    with open(import_path, "w", newline="", encoding="utf-8") as import_handle:
        writer = csv.writer(import_handle)
        for row in rows:
            writer.writerow(row)
    return import_path


def _normalize_vocab_key(value: str) -> str:
    return "".join(value.split()).strip()


def _normalize_cloze_key(value: str) -> str:
    return " ".join(value.split()).strip()


def normalize_key_for_label(label: str, value: str) -> str:
    if label == "vocab":
        return _normalize_vocab_key(value)
    return _normalize_cloze_key(value)


def row_key(label: str, row: list[str]) -> str:
    if label == "vocab":
        if len(row) < 3:
            return ""
        return normalize_key_for_label(label, row[2])
    if not row:
        return ""
    return normalize_key_for_label(label, row[0])


def row_quality(label: str, row: list[str]) -> tuple[int, int]:
    if label == "vocab":
        cells = row + [""] * max(0, 5 - len(row))
        english, pinyin, _simplified, traditional, audio = (cell.strip() for cell in cells[:5])
        non_empty = sum(1 for value in (english, pinyin, traditional, audio) if value)
        richness = len(english) + len(pinyin) + len(audio)
        return non_empty, richness
    text = row[0].strip() if row else ""
    return (1 if text else 0, len(text))


def read_data_rows(path: Path) -> list[list[str]]:
    rows = read_csv_rows(path)
    if not rows:
        return []
    normalized_first_row = tuple(cell.strip() for cell in rows[0])
    if normalized_first_row in KNOWN_HEADER_ROWS:
        return rows[1:]
    return rows


def dedupe_import_rows(label: str, rows: list[list[str]]) -> tuple[list[list[str]], int]:
    deduped: list[list[str]] = []
    key_to_index: dict[str, int] = {}
    removed = 0
    for row in rows:
        key = row_key(label, row)
        if not key:
            continue
        existing_index = key_to_index.get(key)
        if existing_index is None:
            key_to_index[key] = len(deduped)
            deduped.append(row)
            continue
        removed += 1
        existing = deduped[existing_index]
        if row_quality(label, row) >= row_quality(label, existing):
            deduped[existing_index] = row
    return deduped, removed


def filter_rows_by_deleted_keys(
    *,
    label: str,
    rows: list[list[str]],
    deleted_keys: set[str],
) -> tuple[list[list[str]], int]:
    if not deleted_keys:
        return rows, 0
    kept: list[list[str]] = []
    skipped = 0
    for row in rows:
        key = row_key(label, row)
        if key and key in deleted_keys:
            skipped += 1
            continue
        kept.append(row)
    return kept, skipped


def _field_name_for_label(label: str) -> str:
    if label == "vocab":
        return VOCAB_FIELD_NAME
    return CLOZE_FIELD_NAME


def _field_index_for_model(model: dict[str, Any], field_name: str) -> int | None:
    fields = model.get("flds")
    if not isinstance(fields, list):
        return None
    target = field_name.strip().lower()
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name", "")).strip().lower()
        if name == target:
            return index
    return None


def _model_for_mid(collection: Any, mid: Any) -> dict[str, Any] | None:
    models = getattr(collection, "models", None)
    if models is None:
        return None
    for getter_name in ("get", "by_id"):
        getter = getattr(models, getter_name, None)
        if not callable(getter):
            continue
        for candidate in (mid, str(mid)):
            try:
                model = getter(candidate)
            except Exception:
                continue
            if isinstance(model, dict):
                return model
    return None


def existing_key_index(collection: Any, label: str) -> dict[str, list[int]]:
    db = getattr(collection, "db", None)
    if db is None:
        return {}
    all_rows = getattr(db, "all", None)
    if not callable(all_rows):
        return {}

    try:
        note_rows = all_rows("select id, mid, flds from notes")
    except Exception:
        return {}

    field_name = _field_name_for_label(label)
    mid_to_field_index: dict[Any, int | None] = {}
    keys: dict[str, list[int]] = {}
    for row in note_rows:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        note_id = int(row[0])
        mid = row[1]
        flds = str(row[2] or "")

        if mid not in mid_to_field_index:
            model = _model_for_mid(collection, mid)
            mid_to_field_index[mid] = _field_index_for_model(model or {}, field_name)
        field_index = mid_to_field_index[mid]
        if field_index is None:
            continue

        values = flds.split(FIELD_SEPARATOR)
        if field_index >= len(values):
            continue
        key = normalize_key_for_label(label, values[field_index])
        if not key:
            continue
        keys.setdefault(key, []).append(note_id)
    return keys


def remove_note_ids(collection: Any, note_ids: Iterable[int]) -> int:
    unique_ids = sorted({int(note_id) for note_id in note_ids})
    if not unique_ids:
        return 0
    for method_name in ("remove_notes", "remNotes"):
        method = getattr(collection, method_name, None)
        if callable(method):
            method(unique_ids)
            return len(unique_ids)
    raise RuntimeError("Collection does not support note deletion")


def _deleted_keys_path(base_dir: Path) -> Path:
    return base_dir / DELETED_KEYS_FILENAME


def load_deleted_keys(base_dir: Path) -> dict[str, set[str]]:
    path = _deleted_keys_path(base_dir)
    if not path.exists():
        return {"vocab": set(), "cloze": set()}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"vocab": set(), "cloze": set()}
    if not isinstance(payload, dict):
        return {"vocab": set(), "cloze": set()}
    vocab_values = payload.get("vocab", [])
    cloze_values = payload.get("cloze", [])
    vocab = {
        normalize_key_for_label("vocab", str(value))
        for value in vocab_values
        if str(value).strip()
    }
    cloze = {
        normalize_key_for_label("cloze", str(value))
        for value in cloze_values
        if str(value).strip()
    }
    return {"vocab": vocab, "cloze": cloze}


def save_deleted_keys(base_dir: Path, deleted_keys: dict[str, set[str]]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    path = _deleted_keys_path(base_dir)
    payload = {
        "vocab": sorted(deleted_keys.get("vocab", set())),
        "cloze": sorted(deleted_keys.get("cloze", set())),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_deleted_keys(base_dir: Path, keys_by_label: dict[str, set[str]]) -> int:
    deleted_keys = load_deleted_keys(base_dir)
    before = sum(len(deleted_keys[label]) for label in ("vocab", "cloze"))
    for label in ("vocab", "cloze"):
        deleted_keys[label].update(keys_by_label.get(label, set()))
    after = sum(len(deleted_keys[label]) for label in ("vocab", "cloze"))
    if after != before:
        save_deleted_keys(base_dir, deleted_keys)
    return after - before


def _managed_notes_path(base_dir: Path) -> Path:
    return base_dir / MANAGED_NOTES_FILENAME


def load_managed_notes(base_dir: Path) -> dict[str, dict[str, set[int]]]:
    path = _managed_notes_path(base_dir)
    if not path.exists():
        return {"vocab": {}, "cloze": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"vocab": {}, "cloze": {}}
    if not isinstance(payload, dict):
        return {"vocab": {}, "cloze": {}}

    managed: dict[str, dict[str, set[int]]] = {"vocab": {}, "cloze": {}}
    for label in ("vocab", "cloze"):
        raw_label_map = payload.get(label, {})
        if not isinstance(raw_label_map, dict):
            continue
        for raw_key, raw_note_ids in raw_label_map.items():
            key = normalize_key_for_label(label, str(raw_key))
            if not key:
                continue
            if not isinstance(raw_note_ids, list):
                continue
            note_ids: set[int] = set()
            for raw_note_id in raw_note_ids:
                try:
                    note_id = int(raw_note_id)
                except (TypeError, ValueError):
                    continue
                note_ids.add(note_id)
            if note_ids:
                managed[label][key] = note_ids
    return managed


def save_managed_notes(base_dir: Path, managed_notes: dict[str, dict[str, set[int]]]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    path = _managed_notes_path(base_dir)
    payload: dict[str, dict[str, list[int]]] = {"vocab": {}, "cloze": {}}
    for label in ("vocab", "cloze"):
        label_map = managed_notes.get(label, {})
        if not isinstance(label_map, dict):
            continue
        normalized_map: dict[str, list[int]] = {}
        for key, raw_note_ids in label_map.items():
            normalized_key = normalize_key_for_label(label, str(key))
            if not normalized_key:
                continue
            normalized_note_ids: set[int] = set()
            for raw_note_id in raw_note_ids:
                try:
                    normalized_note_ids.add(int(raw_note_id))
                except (TypeError, ValueError):
                    continue
            note_ids = sorted(normalized_note_ids)
            if note_ids:
                normalized_map[normalized_key] = note_ids
        payload[label] = dict(sorted(normalized_map.items()))

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def managed_key_index(base_dir: Path, label: str) -> dict[str, set[int]]:
    managed = load_managed_notes(base_dir)
    return {key: set(note_ids) for key, note_ids in managed.get(label, {}).items()}


def append_managed_note_ids(
    base_dir: Path,
    *,
    label: str,
    note_ids_by_key: dict[str, set[int]],
) -> int:
    if not note_ids_by_key:
        return 0
    managed_notes = load_managed_notes(base_dir)
    label_map = managed_notes.setdefault(label, {})
    before = sum(len(ids) for ids in label_map.values())
    for raw_key, raw_note_ids in note_ids_by_key.items():
        key = normalize_key_for_label(label, raw_key)
        if not key:
            continue
        if not raw_note_ids:
            continue
        normalized_ids: set[int] = set()
        for raw_note_id in raw_note_ids:
            try:
                normalized_ids.add(int(raw_note_id))
            except (TypeError, ValueError):
                continue
        if not normalized_ids:
            continue
        label_map.setdefault(key, set()).update(normalized_ids)
    after = sum(len(ids) for ids in label_map.values())
    if after != before:
        save_managed_notes(base_dir, managed_notes)
    return after - before


def remove_managed_note_ids(base_dir: Path, note_ids: Iterable[int]) -> int:
    remove_ids = {int(note_id) for note_id in note_ids}
    if not remove_ids:
        return 0
    managed_notes = load_managed_notes(base_dir)
    removed = 0
    for label in ("vocab", "cloze"):
        label_map = managed_notes.get(label, {})
        for key in list(label_map.keys()):
            existing = label_map[key]
            remaining = existing - remove_ids
            removed += len(existing) - len(remaining)
            if remaining:
                label_map[key] = remaining
            else:
                del label_map[key]
    if removed:
        save_managed_notes(base_dir, managed_notes)
    return removed


def collect_imported_note_ids_by_key(
    *,
    label: str,
    rows: list[list[str]],
    key_index_before: dict[str, list[int]],
    key_index_after: dict[str, list[int]],
) -> dict[str, set[int]]:
    imported: dict[str, set[int]] = {}
    seen_keys: set[str] = set()
    for row in rows:
        key = row_key(label, row)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        before = set(key_index_before.get(key, []))
        after = set(key_index_after.get(key, []))
        added = after - before
        if added:
            imported[key] = added
    return imported


def keys_for_note_ids(collection: Any, note_ids: Iterable[int]) -> dict[str, set[str]]:
    ids = sorted({int(note_id) for note_id in note_ids})
    if not ids:
        return {"vocab": set(), "cloze": set()}

    db = getattr(collection, "db", None)
    all_rows = getattr(db, "all", None) if db is not None else None
    if not callable(all_rows):
        return {"vocab": set(), "cloze": set()}

    placeholders = ",".join(str(note_id) for note_id in ids)
    query = f"select id, mid, flds from notes where id in ({placeholders})"
    try:
        note_rows = all_rows(query)
    except Exception:
        return {"vocab": set(), "cloze": set()}

    mid_to_vocab_index: dict[Any, int | None] = {}
    mid_to_cloze_index: dict[Any, int | None] = {}
    keys = {"vocab": set(), "cloze": set()}
    for row in note_rows:
        if not isinstance(row, (list, tuple)) or len(row) < 3:
            continue
        mid = row[1]
        flds = str(row[2] or "")

        if mid not in mid_to_vocab_index:
            model = _model_for_mid(collection, mid) or {}
            mid_to_vocab_index[mid] = _field_index_for_model(model, VOCAB_FIELD_NAME)
            mid_to_cloze_index[mid] = _field_index_for_model(model, CLOZE_FIELD_NAME)

        values = flds.split(FIELD_SEPARATOR)
        vocab_index = mid_to_vocab_index[mid]
        cloze_index = mid_to_cloze_index[mid]

        if vocab_index is not None and vocab_index < len(values):
            vocab_key = normalize_key_for_label("vocab", values[vocab_index])
            if vocab_key:
                keys["vocab"].add(vocab_key)
        if cloze_index is not None and cloze_index < len(values):
            cloze_key = normalize_key_for_label("cloze", values[cloze_index])
            if cloze_key:
                keys["cloze"].add(cloze_key)
    return keys


def filter_rows_by_import_mode(
    *,
    label: str,
    rows: list[list[str]],
    mode: ImportMode,
    key_index: dict[str, list[int]],
    managed_note_ids_by_key: dict[str, set[int]] | None = None,
) -> tuple[list[list[str]], int, list[int]]:
    if mode == "overwrite":
        if managed_note_ids_by_key is None:
            note_ids: list[int] = []
            for row in rows:
                key = row_key(label, row)
                if not key:
                    continue
                note_ids.extend(key_index.get(key, []))
            return rows, 0, note_ids

        kept: list[list[str]] = []
        note_ids: list[int] = []
        protected = 0
        for row in rows:
            key = row_key(label, row)
            if not key:
                kept.append(row)
                continue
            existing_ids = key_index.get(key, [])
            if not existing_ids:
                kept.append(row)
                continue
            managed_ids = managed_note_ids_by_key.get(key, set())
            removable = [note_id for note_id in existing_ids if note_id in managed_ids]
            if removable and len(removable) == len(existing_ids):
                note_ids.extend(removable)
                kept.append(row)
                continue
            protected += 1
        return kept, protected, note_ids

    kept: list[list[str]] = []
    skipped = 0
    for row in rows:
        key = row_key(label, row)
        if key and key in key_index:
            skipped += 1
            continue
        kept.append(row)
    return kept, skipped, []


def count_cards_for_note_ids(collection: Any, note_ids: Iterable[int]) -> int:
    ids = sorted({int(note_id) for note_id in note_ids})
    if not ids:
        return 0
    db = getattr(collection, "db", None)
    if db is None:
        return 0
    scalar = getattr(db, "scalar", None)
    placeholders = ",".join(str(note_id) for note_id in ids)
    query = f"select count(*) from cards where nid in ({placeholders})"
    if callable(scalar):
        try:
            value = scalar(query)
            return int(value or 0)
        except Exception:
            pass
    all_rows = getattr(db, "all", None)
    if not callable(all_rows):
        return 0
    try:
        rows = all_rows(query)
    except Exception:
        return 0
    if not rows:
        return 0
    first_row = rows[0]
    if isinstance(first_row, (list, tuple)) and first_row:
        try:
            return int(first_row[0] or 0)
        except (TypeError, ValueError):
            return 0
    try:
        return int(first_row or 0)
    except (TypeError, ValueError):
        return 0


def _import_history_path(base_dir: Path) -> Path:
    return base_dir / IMPORT_HISTORY_FILENAME


def append_import_history(base_dir: Path, event: dict[str, Any]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(event)
    payload["timestamp_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with open(_import_history_path(base_dir), "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
