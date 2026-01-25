from italki_anki.parser import parse_lines


def test_latin_gloss_attached_to_previous_chinese():
    text = "书房\nstudy\n微积分"
    lines = parse_lines(text.splitlines())
    assert len(lines) == 2
    assert lines[0].text == "书房"
    assert lines[0].gloss == "study"
    assert lines[1].text == "微积分"
    assert lines[1].gloss is None
