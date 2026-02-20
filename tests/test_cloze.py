import pytest

from italki_anki.cloze import align_chunks, align_pinyin_chunks, build_cloze_lines, segment_text


def test_variable_length_cloze_segmentation():
    lines = build_cloze_lines(
        english="Can you keep this seat for me?",
        simplified="你可以帮我保留这个座位吗？",
        traditional="你可以幫我保留這個座位嗎？",
        pinyin="nǐ kěyǐ bāng wǒ bǎoliú zhège zuòwèi ma",
        max_len=4,
    )
    assert len(lines.simplified_chunks) >= 3
    assert all(len(chunk) <= 4 for chunk in lines.simplified_chunks[:-1])
    assert len(lines.simplified_chunks) == len(lines.traditional_chunks)
    assert len(lines.simplified_chunks) == len(lines.pinyin_chunks)


def test_pinyin_alignment_respects_sentence_boundaries():
    lines = build_cloze_lines(
        english="Thank you, teacher! See you next time.",
        simplified="感谢老师！下次见",
        traditional="感謝老師！下次見",
        pinyin="gǎn xiè lǎo shī! xià cì jiàn",
        max_len=8,
    )
    assert lines.simplified_chunks == ["感谢老师！", "下次见"]
    assert lines.traditional_chunks == ["感謝老師！", "下次見"]
    assert lines.pinyin_chunks == ["gǎn xiè lǎo shī!", "xià cì jiàn"]


def test_segment_text_requires_positive_max_len():
    with pytest.raises(ValueError, match="max_len must be positive"):
        segment_text("你好", 0)


def test_align_pinyin_chunks_appends_leftover_to_last_chunk():
    chunks = align_pinyin_chunks("nǐ hǎo ma", [1, 1])
    assert chunks == ["nǐ", "hǎo ma"]


def test_align_chunks_appends_remaining_text_to_last_chunk():
    chunks = align_chunks("你好啊", [1, 1])
    assert chunks == ["你", "好啊"]
