from __future__ import annotations

import re
from typing import Iterable, List, Optional

from .models import RawLine

URL_RE = re.compile(r"https?://\S+")
TIMESTAMP_RE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\s*$")
EMOJI_ONLY_RE = re.compile(r"^[\W_]+$")
LATIN_ONLY_RE = re.compile(r"^[A-Za-z0-9\s'\-.,!?]+$")

GREETINGS = {
    "hi",
    "hello",
    "hey",
    "谢谢",
    "老师好",
    "早上好",
    "晚上好",
}


def normalize_line(line: str) -> str:
    return line.strip()


def is_noise_line(line: str) -> bool:
    if not line:
        return True
    if TIMESTAMP_RE.match(line):
        return True
    if URL_RE.search(line):
        return True
    if line.lower() in GREETINGS:
        return True
    if EMOJI_ONLY_RE.match(line) and not re.search(r"[\u4e00-\u9fff]", line):
        return True
    return False


def is_latin_only(line: str) -> bool:
    return bool(LATIN_ONLY_RE.match(line))


def is_chinese_line(line: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", line))


def parse_lines(lines: Iterable[str]) -> List[RawLine]:
    cleaned: List[str] = []
    for line in lines:
        normalized = normalize_line(line)
        if is_noise_line(normalized):
            continue
        cleaned.append(normalized)

    raw_lines: List[RawLine] = []
    latin_buffer: List[int] = []
    for idx, line in enumerate(cleaned):
        if is_latin_only(line) and not is_chinese_line(line):
            latin_buffer.append(idx)
            raw_lines.append(RawLine(text=line))
        else:
            raw_lines.append(RawLine(text=line))

    attached = attach_glosses(raw_lines, latin_buffer)
    return [item for item in attached if is_chinese_line(item.text)]


def attach_glosses(raw_lines: List[RawLine], latin_indices: List[int]) -> List[RawLine]:
    updated = raw_lines[:]
    for idx in latin_indices:
        gloss = updated[idx].text
        target = find_nearest_chinese_index(updated, idx)
        if target is None:
            continue
        target_item = updated[target]
        updated[target] = RawLine(text=target_item.text, gloss=gloss)
    return updated


def find_nearest_chinese_index(lines: List[RawLine], idx: int) -> Optional[int]:
    for back in range(idx - 1, -1, -1):
        if is_chinese_line(lines[back].text):
            return back
    for forward in range(idx + 1, len(lines)):
        if is_chinese_line(lines[forward].text):
            return forward
    return None
