from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Literal

RunMode = Literal["latest", "archive", "both"]

VOCAB_FILENAME = "vocab_cards.csv"
CLOZE_FILENAME = "cloze_cards.csv"
AUDIO_DIRNAME = "audio"
MANIFEST_FILENAME = "latest_run.json"
RUNS_DIRNAME = "runs"


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_mode: RunMode
    output_root: Path
    build_dir: Path


def generate_run_id(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    # Millisecond precision keeps run IDs human-readable while avoiding collisions.
    return stamp.strftime("%Y%m%d-%H%M%S-%f")[:-3]


def create_run_context(output_root: Path, run_mode: RunMode) -> RunContext:
    normalized_root = output_root.expanduser()
    run_id = generate_run_id()
    if run_mode == "latest":
        build_dir = normalized_root
    else:
        build_dir = normalized_root / RUNS_DIRNAME / run_id
    return RunContext(
        run_id=run_id,
        run_mode=run_mode,
        output_root=normalized_root,
        build_dir=build_dir,
    )


def publish_latest_artifacts(run_dir: Path, output_root: Path, include_audio: bool) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for filename in (VOCAB_FILENAME, CLOZE_FILENAME):
        source = run_dir / filename
        target = output_root / filename
        if source.exists():
            shutil.copy2(source, target)
        else:
            target.unlink(missing_ok=True)

    if include_audio:
        source_audio = run_dir / AUDIO_DIRNAME
        target_audio = output_root / AUDIO_DIRNAME
        if target_audio.exists():
            shutil.rmtree(target_audio)
        if source_audio.exists():
            shutil.copytree(source_audio, target_audio)


def write_latest_run_manifest(
    context: RunContext,
    vocab_count: int,
    cloze_count: int,
    include_audio: bool,
    published_latest: bool,
) -> Path:
    context.output_root.mkdir(parents=True, exist_ok=True)
    build_vocab = context.build_dir / VOCAB_FILENAME
    build_cloze = context.build_dir / CLOZE_FILENAME
    build_audio = context.build_dir / AUDIO_DIRNAME
    latest_vocab = context.output_root / VOCAB_FILENAME
    latest_cloze = context.output_root / CLOZE_FILENAME
    latest_audio = context.output_root / AUDIO_DIRNAME

    payload = {
        "run_id": context.run_id,
        "run_mode": context.run_mode,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "output_root": str(context.output_root),
        "build_dir": str(context.build_dir),
        "published_latest": published_latest,
        "include_audio": include_audio,
        "vocab_count": vocab_count,
        "cloze_count": cloze_count,
        "artifacts": {
            "build_vocab_csv": str(build_vocab) if build_vocab.exists() else None,
            "build_cloze_csv": str(build_cloze) if build_cloze.exists() else None,
            "build_audio_dir": str(build_audio) if build_audio.exists() else None,
            "latest_vocab_csv": str(latest_vocab) if latest_vocab.exists() else None,
            "latest_cloze_csv": str(latest_cloze) if latest_cloze.exists() else None,
            "latest_audio_dir": str(latest_audio) if latest_audio.exists() else None,
        },
    }

    manifest_path = context.output_root / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path
