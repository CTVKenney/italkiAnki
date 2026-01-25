from __future__ import annotations

import argparse
from pathlib import Path

from .audio import NullAudioProvider, PollyAudioProvider
from .builder import build_from_text
from .cards import BuildConfig
from .llm import LLMClient


class UnconfiguredLLM(LLMClient):
    def classify(self, lines, seed=None):
        raise RuntimeError(
            "LLM client not configured. Provide an implementation of LLMClient."
        )


def build_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_dir = Path(args.out_dir)
    text = input_path.read_text(encoding="utf-8")

    config = BuildConfig(
        max_cloze_len=args.max_cloze_len,
        seed=args.seed,
        include_audio=not args.no_audio,
    )

    if args.no_audio:
        audio = NullAudioProvider(output_dir=str(output_dir / "audio"))
    else:
        audio = PollyAudioProvider(output_dir=str(output_dir / "audio"))

    llm = UnconfiguredLLM()

    build_from_text(text, llm, audio, str(output_dir), config)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="italki_anki")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="Build Anki CSVs from lesson text")
    build.add_argument("input", help="Input UTF-8 text file")
    build.add_argument("--out-dir", default="output", help="Output directory")
    build.add_argument("--seed", type=int, default=None, help="Deterministic randomness")
    build.add_argument("--no-audio", action="store_true", help="Skip audio generation")
    build.add_argument(
        "--max-cloze-len",
        type=int,
        default=8,
        help="Soft limit per cloze chunk",
    )
    build.set_defaults(func=build_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
