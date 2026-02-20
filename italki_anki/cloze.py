from __future__ import annotations

import re
from typing import Iterable, List

from .models import ClozeLines

PUNCTUATION = set("，。？！；、,.?!")
CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


PINYIN_NUMBERS = {
    1: "yī",
    2: "èr",
    3: "sān",
    4: "sì",
    5: "wǔ",
    6: "liù",
    7: "qī",
    8: "bā",
    9: "jiǔ",
    10: "shí",
}


def segment_text(text: str, max_len: int) -> List[str]:
    if max_len <= 0:
        raise ValueError("max_len must be positive")

    chunks: List[str] = []
    buffer = ""
    for char in text:
        buffer += char
        if char in PUNCTUATION:
            chunks.append(buffer)
            buffer = ""
            continue
        if len(buffer) >= max_len:
            chunks.append(buffer)
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return chunks


def align_pinyin_chunks(pinyin: str, sizes: Iterable[int]) -> List[str]:
    syllables = pinyin.split()
    result = []
    index = 0
    for size in sizes:
        if index + size > len(syllables):
            size = max(len(syllables) - index, 0)
        segment = syllables[index : index + size]
        result.append(" ".join(segment))
        index += size
    if index < len(syllables):
        leftover = " ".join(syllables[index:])
        if result:
            result[-1] = " ".join([result[-1], leftover]).strip()
        else:
            result.append(leftover)
    return result


def count_chinese_chars(text: str) -> int:
    return len(CHINESE_CHAR_RE.findall(text))


def build_cloze_lines(
    english: str,
    simplified: str,
    traditional: str,
    pinyin: str,
    max_len: int,
) -> ClozeLines:
    simplified_chunks = segment_text(simplified, max_len)
    sizes = [len(chunk) for chunk in simplified_chunks]
    pinyin_sizes = [count_chinese_chars(chunk) for chunk in simplified_chunks]
    if sum(pinyin_sizes) == 0:
        pinyin_sizes = sizes
    traditional_chunks = align_chunks(traditional, sizes)
    pinyin_chunks = align_pinyin_chunks(pinyin, pinyin_sizes)
    return ClozeLines(
        english=english,
        simplified_chunks=simplified_chunks,
        traditional_chunks=traditional_chunks,
        pinyin_chunks=pinyin_chunks,
    )


def align_chunks(text: str, sizes: Iterable[int]) -> List[str]:
    chunks: List[str] = []
    start = 0
    for size in sizes:
        end = start + size
        chunks.append(text[start:end])
        start = end
    if start < len(text):
        chunks[-1] += text[start:]
    return chunks


def render_cloze(lines: ClozeLines) -> str:
    return "\n".join(render_cloze_lines(lines))


def render_cloze_lines(lines: ClozeLines) -> List[str]:
    simplified = render_cloze_line(lines.simplified_chunks)
    traditional = render_cloze_line(lines.traditional_chunks)
    output = [lines.english, simplified, traditional]
    if lines.pinyin_chunks and any(chunk.strip() for chunk in lines.pinyin_chunks):
        output.append(render_cloze_line(lines.pinyin_chunks))
    return output


def render_cloze_line(chunks: Iterable[str]) -> str:
    rendered = []
    for idx, chunk in enumerate(chunks, start=1):
        rendered.append(f"{{{{c{idx}::{chunk}}}}}")
    return "".join(rendered)
