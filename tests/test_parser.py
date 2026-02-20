from italki_anki.parser import parse_lines


def test_latin_gloss_attached_to_previous_chinese():
    text = "书房\nstudy\n微积分"
    lines = parse_lines(text.splitlines())
    assert len(lines) == 2
    assert lines[0].text == "书房"
    assert lines[0].gloss == "study"
    assert lines[1].text == "微积分"
    assert lines[1].gloss is None


def test_filters_metadata_and_dedupes_chinese_items():
    text = "\n".join(
        [
            "中部地区",
            "transcript",
            "听力原文",
            "有声书",
            "音频",
            "下课以后",
            "复习",
            "中部地区",
        ]
    )
    lines = parse_lines(text.splitlines())
    assert [line.text for line in lines] == ["中部地区", "有声书", "下课以后", "复习"]


def test_channel_name_line_is_filtered_instead_of_becoming_gloss():
    text = "书房\nMandarin Corner\n微积分"
    lines = parse_lines(text.splitlines())
    assert len(lines) == 2
    assert lines[0].text == "书房"
    assert lines[0].gloss is None
    assert lines[1].text == "微积分"


def test_filters_teacher_signoff_chatter_in_chinese_and_english():
    text = "\n".join(
        [
            "感谢老师！下次见",
            "Thank you, teacher! See you next time.",
            "书房",
            "study",
        ]
    )
    lines = parse_lines(text.splitlines())
    assert len(lines) == 1
    assert lines[0].text == "书房"
    assert lines[0].gloss == "study"
