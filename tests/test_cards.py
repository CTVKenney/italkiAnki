from italki_anki.cards import BuildConfig, ClozeNote, VocabCard, build_vocab_cards, dedupe_cloze_notes, dedupe_vocab_cards
from italki_anki.models import ClassifiedItem, ItemType
from italki_anki.audio import NullAudioProvider


def test_degree_word_stripping():
    item = ClassifiedItem(
        item_type=ItemType.VOCAB,
        simplified="太咸",
        traditional="太鹹",
        pinyin="tài xián",
        english="too salty",
    )
    cards = build_vocab_cards([item], NullAudioProvider(output_dir="."), BuildConfig())
    assert cards[0].simplified == "咸"
    assert cards[0].traditional == "鹹"


def test_measure_word_exception_for_ge():
    item = ClassifiedItem(
        item_type=ItemType.VOCAB,
        simplified="水瓶",
        traditional="水瓶",
        pinyin="shuǐ píng",
        english="water bottle",
        measure_word="个",
        measure_word_pinyin="gè",
    )
    cards = build_vocab_cards(
        [item],
        NullAudioProvider(output_dir="."),
        BuildConfig(seed=3),
    )
    assert cards[0].simplified == "水瓶"
    assert cards[0].english == "water bottle"


def test_deterministic_measure_word_prefix():
    item = ClassifiedItem(
        item_type=ItemType.VOCAB,
        simplified="胡萝卜",
        traditional="胡蘿蔔",
        pinyin="hú luóbo",
        english="carrot",
        measure_word="根",
        measure_word_pinyin="gēn",
    )
    config = BuildConfig(seed=42)
    cards_a = build_vocab_cards([item], NullAudioProvider(output_dir="."), config)
    cards_b = build_vocab_cards([item], NullAudioProvider(output_dir="."), config)
    assert cards_a[0].simplified == cards_b[0].simplified
    assert cards_a[0].pinyin == cards_b[0].pinyin
    assert not any(char.isdigit() for char in cards_a[0].simplified)
    assert cards_a[0].simplified[0] in "一二三四五六七八九十"
    assert cards_a[0].english == cards_b[0].english
    assert cards_a[0].english.startswith("Two ")
    assert cards_a[0].english.endswith("carrots")


def test_dedupe_vocab_cards_prefers_richer_duplicate():
    cards = [
        VocabCard(
            english="",
            pinyin="",
            simplified="长假",
            traditional="長假",
            audio="",
        ),
        VocabCard(
            english="long holiday",
            pinyin="chang2 jia4",
            simplified="长假",
            traditional="長假",
            audio="[sound:a.mp3]",
        ),
    ]

    deduped = dedupe_vocab_cards(cards)

    assert len(deduped) == 1
    assert deduped[0].pinyin == "chang2 jia4"
    assert deduped[0].audio == "[sound:a.mp3]"


def test_dedupe_cloze_notes_drops_duplicate_text():
    notes = [
        ClozeNote(text="{{c1::你好}}\n{{c2::老师}}"),
        ClozeNote(text="{{c1::你好}}\n{{c2::老师}}"),
    ]

    deduped = dedupe_cloze_notes(notes)

    assert len(deduped) == 1
