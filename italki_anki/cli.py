from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Callable, Sequence

from .builder import build_from_text, pick_audio_provider
from .cards import BuildConfig
from .llm import LLMClient, StubClient, openai_client_from_env
from .runs import RunMode, create_run_context, publish_latest_artifacts, write_latest_run_manifest
from .tone_ai import (
    DEFAULT_TONE_MODEL_ID,
    AutocorrelationTone34Classifier,
    HFWav2Vec2PinyinToneClassifier,
    ToneAIError,
    ToneClassifier,
    evaluate_tone_classifier,
    load_tone_eval_samples,
    write_tone_eval_json,
)


DEFAULT_EDITOR = "vi"


def normalize_legacy_argv(argv: Sequence[str]) -> list[str]:
    if not argv or argv[0] != "build":
        return list(argv)
    remainder = list(argv[1:])
    if remainder and not remainder[0].startswith("-"):
        return ["--input", remainder[0], *remainder[1:]]
    return remainder


def read_text_from_editor(initial_text: str = "") -> str:
    editor = os.getenv("EDITOR") or DEFAULT_EDITOR
    command = shlex.split(editor)
    if not command:
        raise RuntimeError("EDITOR is empty")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            delete=False,
        ) as handle:
            if initial_text:
                handle.write(initial_text)
            temp_path = Path(handle.name)

        completed = subprocess.run([*command, str(temp_path)], check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"Editor exited with status {completed.returncode}")
        return temp_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"Editor not found: {command[0]}") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def resolve_input_text(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    if args.interactive:
        return read_text_from_editor()
    if args.stdin:
        return sys.stdin.read()
    if args.input:
        return Path(args.input).read_text(encoding="utf-8")
    parser.error("one of --interactive, --stdin, or --input is required")
    return ""


def select_llm(args: argparse.Namespace) -> LLMClient:
    if args.openai:
        return openai_client_from_env()
    return StubClient()


def build_status_reporter() -> tuple[Callable[[str], None], Callable[[], float]]:
    started = time.monotonic()
    state = {"step": 0}

    def report(message: str) -> None:
        state["step"] += 1
        elapsed = time.monotonic() - started
        print(f"[{state['step']}] {message} ({elapsed:.1f}s)", file=sys.stderr)

    def elapsed_seconds() -> float:
        return time.monotonic() - started

    return report, elapsed_seconds


def build_tone_classifier(args: argparse.Namespace) -> ToneClassifier:
    if args.tone_backend == "autocorr-3-4":
        return AutocorrelationTone34Classifier()
    if args.tone_backend == "hf-wav2vec2-pinyin":
        return HFWav2Vec2PinyinToneClassifier(
            model_id=args.tone_model_id,
            device=args.tone_device,
            syllable_index=args.tone_syllable_index,
            allow_neutral_tone=args.tone_allow_neutral,
        )
    raise ToneAIError(f"unsupported tone backend: {args.tone_backend}")


def tone_eval_command(args: argparse.Namespace) -> int:
    samples = load_tone_eval_samples(args.tone_eval_tsv)
    classifier = build_tone_classifier(args)
    summary, records = evaluate_tone_classifier(classifier, samples)
    print(f"Tone backend: {args.tone_backend}", file=sys.stderr)
    if args.tone_backend == "hf-wav2vec2-pinyin":
        print(f"Tone model: {args.tone_model_id}", file=sys.stderr)
    print(
        f"Tone eval: total={summary.total} predicted={summary.predicted} "
        f"correct={summary.correct} accuracy={summary.accuracy:.4f}",
        file=sys.stderr,
    )
    for tone in range(1, 6):
        stats = summary.per_tone[tone]
        print(
            f"  tone {tone}: n={int(stats['n'])} "
            f"correct={int(stats['correct'])} accuracy={float(stats['accuracy']):.4f}",
            file=sys.stderr,
        )

    errors = [record for record in records if record.error]
    if errors:
        print(f"Prediction failures: {len(errors)}", file=sys.stderr)
        for record in errors[:10]:
            print(f"  {record.audio_path}: {record.error}", file=sys.stderr)

    if args.tone_eval_json_out:
        output_path = write_tone_eval_json(args.tone_eval_json_out, summary, records)
        print(f"Wrote tone eval JSON: {output_path}", file=sys.stderr)
    return 0 if not errors else 2


def build_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    output_root = Path(args.out_dir)
    text = resolve_input_text(args, parser)
    if not text.strip():
        parser.error("input is empty")

    config = BuildConfig(
        max_cloze_len=args.max_cloze_len,
        seed=args.seed,
        include_audio=args.audio,
    )

    run_mode: RunMode = args.run_mode
    run_context = create_run_context(output_root, run_mode)
    audio = pick_audio_provider(
        output_dir=str(run_context.build_dir / "audio"),
        include_audio=args.audio,
    )
    status_reporter, elapsed_seconds = build_status_reporter()
    llm = select_llm(args)
    if args.openai:
        status_reporter("Classifier: OpenAI")
    else:
        status_reporter("Classifier: stub heuristic (--openai disabled; output may be noisy)")
    status_reporter(f"Run ID: {run_context.run_id}")
    status_reporter(f"Run mode: {run_context.run_mode}")
    status_reporter(f"Build output directory: {run_context.build_dir}")

    result = build_from_text(
        text,
        llm,
        audio,
        str(run_context.build_dir),
        config,
        status=status_reporter,
    )
    published_latest = run_context.run_mode in {"latest", "both"}
    if run_context.run_mode == "both":
        status_reporter("Publishing latest artifacts")
        publish_latest_artifacts(
            run_context.build_dir,
            run_context.output_root,
            include_audio=args.audio,
        )
    manifest_path = write_latest_run_manifest(
        run_context,
        vocab_count=result.vocab_count,
        cloze_count=result.cloze_count,
        include_audio=args.audio,
        published_latest=published_latest,
    )
    status_reporter(f"Wrote run manifest: {manifest_path}")

    if run_context.run_mode == "archive":
        destination = run_context.build_dir
        destination_label = "archive run"
    elif run_context.run_mode == "both":
        destination = run_context.output_root
        destination_label = "latest output (archive also written)"
    else:
        destination = run_context.output_root
        destination_label = "latest output"
    print(
        f"Wrote {result.vocab_count} vocab cards and "
        f"{result.cloze_count} cloze notes to {destination} "
        f"({destination_label}) "
        f"in {elapsed_seconds():.1f}s"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="italki-anki",
        description="Build Anki CSVs from raw italki chat text.",
    )
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--interactive",
        action="store_true",
        help="Open $EDITOR to paste raw chat text.",
    )
    source_group.add_argument(
        "--stdin",
        action="store_true",
        help="Read raw chat text from standard input.",
    )
    source_group.add_argument(
        "--input",
        help="Path to a UTF-8 text file containing raw chat text.",
    )
    parser.add_argument("--out-dir", default="output", help="Output directory")
    parser.add_argument(
        "--run-mode",
        choices=("latest", "archive", "both"),
        default="both",
        help=(
            "Output lifecycle mode: latest=overwrite root files, "
            "archive=write timestamped run only, both=archive and publish root files"
        ),
    )
    parser.add_argument("--seed", type=int, default=None, help="Deterministic randomness")
    audio_group = parser.add_mutually_exclusive_group()
    audio_group.add_argument(
        "--audio",
        action="store_true",
        help="Generate audio files using Amazon Polly.",
    )
    audio_group.add_argument("--no-audio", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--max-cloze-len",
        type=int,
        default=8,
        help="Soft limit per cloze chunk",
    )
    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument(
        "--openai",
        action="store_true",
        help="Use OpenAI API for classification (requires OPENAI_API_KEY)",
    )
    llm_group.add_argument(
        "--stub-llm",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--tone-eval-tsv",
        help="Evaluate tone classifier on TSV/CSV rows: <audio_path><tab><expected_tone>.",
    )
    parser.add_argument(
        "--tone-eval-json-out",
        help="Optional JSON output path for --tone-eval-tsv detailed results.",
    )
    parser.add_argument(
        "--tone-backend",
        choices=("hf-wav2vec2-pinyin", "autocorr-3-4"),
        default="hf-wav2vec2-pinyin",
        help="Tone backend for --tone-eval-tsv.",
    )
    parser.add_argument(
        "--tone-model-id",
        default=DEFAULT_TONE_MODEL_ID,
        help="Hugging Face model id for hf-wav2vec2-pinyin backend.",
    )
    parser.add_argument(
        "--tone-device",
        default="cpu",
        help="Torch device for hf-wav2vec2-pinyin backend (for example: cpu, cuda).",
    )
    parser.add_argument(
        "--tone-syllable-index",
        type=int,
        default=-1,
        help="Syllable index used when multiple tones are detected in transcript (default: -1).",
    )
    parser.add_argument(
        "--tone-allow-neutral",
        action="store_true",
        help="Allow tone 5 predictions in hf-wav2vec2-pinyin backend.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(normalize_legacy_argv(raw_argv))
    try:
        if args.tone_eval_tsv:
            return tone_eval_command(args)
        return build_command(args, parser)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
