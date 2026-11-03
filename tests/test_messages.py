"""said_to keyword matching (pilot round 1, hl-dev-000013): a Korean verb stem keyword matches its conjugated
forms ('나가' in '나간다고'), the wordings people use for the messages are covered, and every canonical message
text still matches only its own key."""
import pytest

from homeloop_robot.catalog import MESSAGE_TEXT, MESSAGES, _has_keyword, message_matches


@pytest.mark.parametrize("key,text,lang", [
    ("leaving_soon", "10분 있다가 나간다고 합니다.", "ko"),
    ("leaving_soon", "10분 후에 나갈 거예요.", "ko"),
    ("leaving_soon", "곧 나갑니다.", "ko"),
    ("leaving_soon", "10분 뒤에 출발해요.", "ko"),
    ("come_kitchen", "주방으로 오시라고 하셨어요.", "ko"),
    ("come_kitchen", "주방으로 오라고 하세요.", "ko"),
    ("dinner_ready", "저녁 다 됐어요.", "ko"),
    ("lunch_ready", "점심 드시래요.", "ko"),
    ("drink_water", "물 좀 드시래요.", "ko"),
    ("tv_off", "텔레비전 끄시래요.", "ko"),
    ("phone_call", "There's a call for you.", "en"),
    ("phone_call", "Someone is on the phone for you.", "en"),
    ("come_kitchen", "Please head to the kitchen.", "en"),
    ("lunch_ready", "Grandpa, come for lunch.", "en"),
    ("drink_water", "Please have some water.", "en"),
])
def test_message_wordings(key, text, lang):
    assert message_matches(key, text, lang)


@pytest.mark.parametrize("key,text,lang", [
    ("leaving_soon", "10분 있다가 와요.", "ko"),
    ("come_kitchen", "거실로 오세요.", "ko"),
    ("dinner_ready", "점심 됐어요.", "ko"),
    ("tv_off", "텔레비전 켜 주세요.", "ko"),
    ("phone_call", "Your phone is on the table.", "en"),
    ("come_kitchen", "I will put the mug in the kitchen.", "en"),
    ("drink_water", "The water bottle is in the fridge.", "en"),
])
def test_other_sentences_do_not_match(key, text, lang):
    assert not message_matches(key, text, lang)


def test_korean_keyword_rules():
    assert _has_keyword("나간다고", "나가")                # stem + ending final (ㄴ)
    assert _has_keyword("나갔어요", "나가")                # ㅆ
    assert not _has_keyword("나각", "나가")                # ㄱ is not a verb-ending final
    assert not _has_keyword("야", "약")                    # a keyword with a final consonant: exact only
    assert not _has_keyword("악아", "가")                  # a final consonant never starts a keyword


def test_canonical_texts_match_only_their_key():
    for k, by_lang in MESSAGE_TEXT.items():
        for lang, t in by_lang.items():
            assert message_matches(k, t, lang), (k, lang)
            assert [k2 for k2 in MESSAGES if k2 != k and message_matches(k2, t, lang)] == [], (k, lang, t)
