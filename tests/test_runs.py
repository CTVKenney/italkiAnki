from __future__ import annotations

import json
from pathlib import Path

from italki_anki.runs import (
    AUDIO_DIRNAME,
    CLOZE_FILENAME,
    VOCAB_FILENAME,
    RunContext,
    create_run_context,
    publish_latest_artifacts,
    write_latest_run_manifest,
)


def test_create_run_context_latest_uses_output_root(tmp_path):
    context = create_run_context(tmp_path, "latest")
    assert context.build_dir == tmp_path
    assert context.run_mode == "latest"


def test_create_run_context_archive_uses_runs_subdir(tmp_path):
    context = create_run_context(tmp_path, "archive")
    assert context.build_dir.parent == tmp_path / "runs"
    assert context.build_dir.name == context.run_id


def test_publish_latest_artifacts_syncs_csv_and_audio(tmp_path):
    run_dir = tmp_path / "runs" / "run-1"
    latest_dir = tmp_path / "latest"
    run_dir.mkdir(parents=True)
    (run_dir / VOCAB_FILENAME).write_text("vocab", encoding="utf-8")
    (run_dir / CLOZE_FILENAME).write_text("cloze", encoding="utf-8")
    audio_dir = run_dir / AUDIO_DIRNAME
    audio_dir.mkdir()
    (audio_dir / "a.mp3").write_bytes(b"a")
    stale_audio = latest_dir / AUDIO_DIRNAME
    stale_audio.mkdir(parents=True)
    (stale_audio / "stale.mp3").write_bytes(b"x")

    publish_latest_artifacts(run_dir, latest_dir, include_audio=True)

    assert (latest_dir / VOCAB_FILENAME).read_text(encoding="utf-8") == "vocab"
    assert (latest_dir / CLOZE_FILENAME).read_text(encoding="utf-8") == "cloze"
    assert (latest_dir / AUDIO_DIRNAME / "a.mp3").exists()
    assert not (latest_dir / AUDIO_DIRNAME / "stale.mp3").exists()


def test_manifest_tracks_artifacts(tmp_path):
    output_root = tmp_path / "output"
    build_dir = output_root / "runs" / "run-1"
    build_dir.mkdir(parents=True)
    (build_dir / VOCAB_FILENAME).write_text("v", encoding="utf-8")
    context = RunContext(
        run_id="run-1",
        run_mode="archive",
        output_root=output_root,
        build_dir=build_dir,
    )

    manifest_path = write_latest_run_manifest(
        context,
        vocab_count=1,
        cloze_count=0,
        include_audio=False,
        published_latest=False,
    )

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-1"
    assert payload["run_mode"] == "archive"
    assert payload["published_latest"] is False
    assert payload["artifacts"]["build_vocab_csv"].endswith(VOCAB_FILENAME)
    assert payload["artifacts"]["latest_vocab_csv"] is None
