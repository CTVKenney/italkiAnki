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
