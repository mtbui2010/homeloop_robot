"""Question classification and answer content, English and Korean."""
import pytest

from _hs_helpers import FakeWorld
from homeloop_robot.dialog import TEXT, classify, compose, mentioned_objects, mentions, normalize

SPEC = {
    "persona": "adult", "slot": "object", "intended": "mug_2",
    "candidates": [
        {"id": "mug_1", "mentions": {"en": ["red mug", "red one"], "ko": ["빨간 머그컵", "빨간 거"]}},
        {"id": "mug_2", "mentions": {"en": ["blue mug", "blue one"], "ko": ["파란 머그컵", "파란 거"]}},
    ],
    "answer": {"en": "The blue one.", "ko": "파란 거요."},
    "gold_question": {"en": "Which mug, the red one or the blue one?", "ko": "빨간 머그컵이요, 파란 머그컵이요?"},
    "interrupt": None,
}


@pytest.mark.parametrize("q,kind", [
    ("Which mug, the red one or the blue one?", "wh"),
    ("Where is my phone?", "wh"),
    ("Do you mean the blue mug?", "yes_no"),
    ("Should I put it in the fridge?", "yes_no"),
    ("The red one?", "yes_no"),
    ("I will bring the mug.", "other"),
    ("어느 머그컵이요?", "wh"),
    ("휴대폰 어디 있어요?", "wh"),
    ("파란 머그컵 맞아요?", "yes_no"),
    ("냉장고에 넣을까요?", "yes_no"),
    ("가져다 드릴게요.", "other"),
])
def test_classify(q, kind):
    assert classify(q) == kind


def test_normalize_and_mentions():
    assert normalize("  The  RED mug! ", "en") == "the red mug"
    assert normalize("빨간 머그컵", "ko") == "빨간머그컵"
    assert mentions("Is it the red one?", "red one", "en")
    assert not mentions("Is it the tired one?", "red one", "en")
    assert mentions("빨간머그컵 말씀이세요?", "빨간 머그컵", "ko")


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_clarify_wh_gives_intended(lang):
    w = FakeWorld()
    c = compose(SPEC["gold_question"][lang], lang, SPEC, w, knows_location=True)
    assert c.kind == "correct" and c.text == SPEC["answer"][lang] and c.informative
    assert c.wrong_text == TEXT["candidate"][lang].format(mention=SPEC["candidates"][0]["mentions"][lang][0])


def test_clarify_yes_no():
    w = FakeWorld()
    c = compose("Do you mean the blue mug?", "en", SPEC, w, knows_location=True)
    assert c.kind == "yes" and c.text == TEXT["yes"]["en"]
    c = compose("Do you mean the red mug?", "en", SPEC, w, knows_location=True)
    assert c.kind == "no" and c.text == "No, the blue one."
    c = compose("빨간 머그컵 맞아요?", "ko", SPEC, w, knows_location=True)
    assert c.kind == "no" and c.text == "아니요, 파란 거요."


def test_answer_in_episode_language_whatever_the_question():
    w = FakeWorld()
    c = compose("Which mug, the red one or the blue one?", "ko", SPEC, w, knows_location=True)
    assert c.text == "파란 거요."


def test_alternative_question_with_aux():
    w = FakeWorld()
    c = compose("Should I bring the red mug or the blue mug?", "en", SPEC, w, knows_location=True)
    assert c.kind == "correct" and c.text == "The blue one."


def test_location_question():
    w = FakeWorld()
    c = compose("Where is the phone?", "en", None, w, knows_location=True, other_place="counter@kitchen")
    assert c.kind == "correct" and c.text == "It's on the coffee table." and c.wrong_text == "It's on the counter."
    c = compose("약 어디 있어요?", "ko", None, w, knows_location=True)
    assert c.text == "냉장고 안에 있어요."
    c = compose("Where is the phone?", "en", None, w, knows_location=False)
    assert c.kind == "not_sure" and not c.informative


def test_location_ambiguous_uses_intended():
    w = FakeWorld()
    assert sorted(mentioned_objects(w, "Where is the mug?")) == []  # no plain "mug" name in the fake world
    c = compose("Where is the blue mug?", "en", None, w, knows_location=True)
    assert c.text == "It's on the counter."


def test_scripted_answer_for_safety_or_refuse():
    w = FakeWorld()
    spec = {"candidates": [], "answer": {"en": "Put it in the drawer, out of reach.", "ko": "서랍에 넣어 주세요."},
            "wrong_answer": {"en": "On the table is fine.", "ko": "탁자에 두세요."}}
    c = compose("Where should I put the knife?", "en", spec, w, knows_location=True)
    assert c.kind == "correct" and c.text.startswith("Put it") and c.wrong_text == "On the table is fine."
    c = compose("칼을 어디에 둘까요?", "ko", spec, w, knows_location=True)
    assert c.text == "서랍에 넣어 주세요."


def test_not_understood_and_generic():
    w = FakeWorld()
    assert compose("I will go now.", "en", SPEC, w, knows_location=True).text == TEXT["not_sure"]["en"]
    assert compose("Which one?", "en", None, w, knows_location=True).text == TEXT["dont_know"]["en"]
