from __future__ import annotations

import re
from typing import Iterable, List, Optional

from .models import RawLine

URL_RE = re.compile(r"https?://\S+")
TIMESTAMP_RE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\s*$")
EMOJI_ONLY_RE = re.compile(r"^[\W_]+$")
LATIN_ONLY_RE = re.compile(r"^[A-Za-z0-9\s'\-.,!?]+$")
SPACE_RE = re.compile(r"\s+")
CHINESE_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")

GREETINGS = {
    "hi",
    "hello",
    "hey",
    "谢谢",
    "老师好",
    "早上好",
    "晚上好",
}

NOISE_LABELS = {
    "audio",
    "channel",
    "lesson notes",
    "listening transcript",
    "transcript",
    "字幕",
    "听力原文",
    "听力文本",
    "原文",
    "录音",
    "课文",
    "音频",
}

CHANNEL_BRANDS = {
    "bilibili",
    "discord",
    "douyin",
    "italki",
    "telegram",
    "wechat",
    "xiaohongshu",
    "youtube",
}

METADATA_KEYWORDS = (
    "channel",
    "episode",
    "podcast",
    "transcript",
)

SOCIAL_GRATITUDE = ("谢谢", "謝謝", "感谢", "感謝", "多谢", "多謝")
SOCIAL_TEACHER = ("老师", "老師")
SOCIAL_FAREWELL = ("下次见", "下次見", "再见", "再見", "拜拜")
SOCIAL_CHINESE_EXACT = {
    "下次见",
    "下次見",
    "再见",
    "再見",
    "拜拜",
    "老师辛苦了",
    "老師辛苦了",
    "辛苦了老师",
    "辛苦了老師",
}


def normalize_line(line: str) -> str:
    return line.strip()


def canonical_text(line: str) -> str:
    lowered = line.strip().lower()
    lowered = lowered.strip("[]【】()（）{}<>《》\"'`*_-:：|")
    return SPACE_RE.sub(" ", lowered)


def chinese_compact_text(line: str) -> str:
    return "".join(CHINESE_CHAR_RE.findall(line))


def looks_like_title_case_channel_name(line: str) -> bool:
    if not is_latin_only(line):
        return False
    words = [token for token in line.split() if token]
    if len(words) < 2:
        return False
    return all(token[0].isupper() for token in words if token[0].isalpha())


def is_metadata_line(line: str) -> bool:
    canonical = canonical_text(line)
    if not canonical:
        return True
    if canonical in NOISE_LABELS:
        return True
    if canonical in CHANNEL_BRANDS:
        return True
    if canonical.startswith(("transcript ", "audio ", "channel ")):
        return True
    if any(keyword in canonical for keyword in METADATA_KEYWORDS):
        return is_latin_only(line)
    if looks_like_title_case_channel_name(line):
        return True
    return False


def is_latin_social_chatter(line: str) -> bool:
    if not is_latin_only(line):
        return False
    canonical = canonical_text(line)
    thanks = "thank you" in canonical or "thanks" in canonical
    teacher = "teacher" in canonical
    see_you = "see you" in canonical or "next time" in canonical
    if thanks and (teacher or see_you):
        return True
    if teacher and see_you:
        return True
    return False


def is_chinese_social_chatter(line: str) -> bool:
    compact = chinese_compact_text(line)
    if not compact:
        return False
    if compact in SOCIAL_CHINESE_EXACT:
        return True
    has_gratitude = any(token in compact for token in SOCIAL_GRATITUDE)
    has_teacher = any(token in compact for token in SOCIAL_TEACHER)
    has_farewell = any(token in compact for token in SOCIAL_FAREWELL)
    if has_gratitude and has_teacher:
        return True
    if has_gratitude and has_farewell:
        return True
    if compact.endswith(("下次见", "下次見")) and has_gratitude:
        return True
    return False


def is_social_chatter_line(line: str) -> bool:
    if is_latin_social_chatter(line):
        return True
    if is_chinese_social_chatter(line):
        return True
    return False


def is_noise_line(line: str) -> bool:
    if not line:
        return True
    if TIMESTAMP_RE.match(line):
        return True
    if URL_RE.search(line):
        return True
    if is_social_chatter_line(line):
        return True
    if canonical_text(line) in GREETINGS:
        return True
    if is_metadata_line(line):
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

    attached = attach_glosses(raw_lines, latin_buffer)
    chinese_lines = [item for item in attached if is_chinese_line(item.text)]
    return dedupe_chinese_lines(chinese_lines)


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


def dedupe_chinese_lines(lines: List[RawLine]) -> List[RawLine]:
    deduped: List[RawLine] = []
    seen: dict[str, int] = {}
    for line in lines:
        key = normalize_line(line.text)
        seen_index = seen.get(key)
        if seen_index is None:
            seen[key] = len(deduped)
            deduped.append(line)
            continue
        existing = deduped[seen_index]
        if existing.gloss is None and line.gloss:
            deduped[seen_index] = RawLine(text=existing.text, gloss=line.gloss)
    return deduped
