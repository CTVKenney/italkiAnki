from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from typing import Sequence

from .builder import build_from_text, pick_audio_provider
from .cards import BuildConfig
from .llm import LLMClient, StubClient, openai_client_from_env


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


def build_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    output_dir = Path(args.out_dir)
    text = resolve_input_text(args, parser)
    if not text.strip():
        parser.error("input is empty")

    config = BuildConfig(
        max_cloze_len=args.max_cloze_len,
        seed=args.seed,
        include_audio=args.audio,
    )

    audio = pick_audio_provider(output_dir=str(output_dir / "audio"), include_audio=args.audio)
    llm = select_llm(args)

    result = build_from_text(text, llm, audio, str(output_dir), config)
    print(
        f"Wrote {result.vocab_count} vocab cards and "
        f"{result.cloze_count} cloze notes to {output_dir}"
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(normalize_legacy_argv(raw_argv))
    try:
        return build_command(args, parser)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
