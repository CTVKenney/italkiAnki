from italki_anki.cloze import build_cloze_lines


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
