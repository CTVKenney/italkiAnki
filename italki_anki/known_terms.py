from __future__ import annotations

import re
from pathlib import Path

_DEFAULT_TERMS_FILENAME = "known_terms.txt"
_TERM_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")


def default_known_terms_path() -> Path:
    return Path(__file__).resolve().with_name(_DEFAULT_TERMS_FILENAME)


def normalize_known_term(text: str) -> str:
    if not text:
        return ""
    return "".join(_TERM_TOKEN_RE.findall(text.lower()))


def load_known_terms(path: Path | None = None) -> set[str]:
    target_path = path or default_known_terms_path()
    if not target_path.exists():
        return set()
    terms: set[str] = set()
    for raw_line in target_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        normalized = normalize_known_term(line)
        if normalized:
            terms.add(normalized)
    return terms
