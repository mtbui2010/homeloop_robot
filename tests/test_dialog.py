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


def test_where_are_you_gives_the_users_place():
    from homeloop_robot.dialog import asks_user_position
    w = FakeWorld()
    for q in ("Where are you? Which place should I bring it to?", "Where are you now?"):
        assert asks_user_position(q)
        c = compose(q, "en", None, w, knows_location=True, user_place=("sofa@living", False))
        assert (c.kind, c.text, c.informative, c.rule) == ("correct", "I'm at the sofa.", False, "self_position")
    c = compose("지금 어디에 계세요?", "ko", SPEC, w, knows_location=True, user_place=("sofa@living", False))
    assert c.text == "소파에 있어요." and c.rule == "self_position"
    c = compose("어디 계세요?", "ko", None, w, knows_location=True, user_place=("bed@bedroom", True))
    assert c.text == "침대로 가고 있어요."
    c = compose("Where are you?", "ko", None, w, knows_location=True, user_place=("armchair@living", True))
    assert c.text == "안락의자로 가고 있어요."
    # not a question about the user: the old rules
    assert not asks_user_position("Where is the phone?")
    assert compose("Where should I put it?", "en", None, w, knows_location=True,
                   user_place=("sofa@living", False)).rule == "generic_user"
    # without a known position (no user) the question is not understood
    assert compose("Where are you?", "en", None, w, knows_location=True).rule == "generic_user"


def test_korean_directional_particle():
    from homeloop_robot.dialog import _ro
    assert _ro("소파") == "로" and _ro("거실") == "로" and _ro("부엌") == "으로" and _ro("") == "로"


def test_where_are_you_with_a_candidate_is_a_clarification():
    w = FakeWorld()
    c = compose("Where are you, and do you mean the blue mug?", "en", SPEC, w, knows_location=True,
                user_place=("sofa@living", False))
    assert c.rule != "self_position"


# ── answers from what the user asked for (GoalView) ───────────────────────────────────────────────────
WANTS = {"all": [{"pred": "on", "args": ["mug_2", "sink@kitchen"]},
                 {"pred": "held_by", "args": ["phone_1", "grandma"]},
                 {"pred": "open", "args": ["fridge@kitchen"]},
                 {"pred": "unmoved", "args": ["knife_1"]}]}


def _gv(w, wants=WANTS):
    from homeloop_robot.dialog import GoalView
    return GoalView(w, wants, "grandma", lambda pid: {"grandma": "armchair@living", "child": "bed@bedroom"}[pid])


def _ans(q, lang="en", spec=None, **kw):
    w = FakeWorld()
    return compose(q, lang, spec, w, knows_location=True, goal=_gv(w, **kw))


def test_goal_destination_question():
    c = _ans("Where should I put the blue mug?")
    assert (c.kind, c.text, c.rule, c.informative) == ("correct", "On the sink, please.", "goal_destination", True)
    assert _ans("파란 머그컵을 어디에 두면 될까요?", "ko").text == "싱크대 위에 놔 주세요."
    assert _ans("Where should I bring the phone?").text == "Bring it to me, please."
    assert _ans("휴대폰은 어디에 가져다 드릴까요?", "ko").text == "저한테 갖다 주세요."
    # where it is AND where it goes
    c = _ans("Where is the blue mug located, and where should I bring it?")
    assert c.text == "It's on the counter. On the sink, please."
    # "Where is X?" alone is still a location question
    assert _ans("Where is the blue mug?").text == "It's on the counter."
    # a question about an object the user did not ask about is not answered from the request
    assert _ans("Where should I put the fork?").rule == "generic_user"


def test_goal_alternatives_and_choices():
    assert _ans("Should I put the blue mug on the counter or the sink?").text == "On the sink, please."
    assert _ans("Should I bring the phone to you or put it somewhere?").text == "Bring it to me, please."
    c = _ans("Which one do you want: the red mug or the blue mug?")
    assert (c.text, c.rule, c.wrong_text) == ("The blue mug.", "goal_object", "The red mug.")
    c = _ans("Which place do you mean: counter in the kitchen or sink in the kitchen?")
    assert (c.text, c.rule) == ("The sink.", "goal_place")
    # a task's own clarification candidates still come first
    assert _ans("Which mug, the red one or the blue one?", spec=SPEC).rule == "clarify_answer"


def test_goal_read_back():
    ok = "I will put the blue mug on the sink in the kitchen, then bring the phone to you, then open the fridge. Is that right?"
    c = _ans(ok)
    assert (c.kind, c.text, c.rule) == ("yes", "Yes, that's right.", "goal_confirm") and c.wrong_text == "No."
    # the robot's plan keys are read as words; the user's own seat counts as "to me"
    c = _ans("I will put the blue mug on the sink@kitchen, then put the phone on the armchair, then open the "
             "fridge@kitchen. Is that right?")
    assert c.kind == "yes"
    c = _ans("I will put the blue mug on the counter in the kitchen, then bring the phone to you, then open the "
             "fridge. Is that right?")
    assert (c.kind, c.text, c.rule) == ("no", "No, put the blue mug on the sink.", "goal_correct")
    c = _ans("I will put the blue mug on the sink. Is that right?")          # forgot the phone and the fridge
    assert c.text == "No, bring the phone to me."
    c = _ans("파란 머그컵을 조리대에 두겠습니다. 맞죠?", "ko")
    assert c.kind == "no" and c.text == "아니요, 파란 머그컵은 싱크대 위에 놔 주세요."
    # a yes / no question about one part of the request
    assert _ans("Do you want me to put the blue mug on the sink?").kind == "yes"
    assert _ans("Should I open the fridge?").kind == "yes"
    # nothing of the request in the question: not answered from it
    assert _ans("Is it raining?").rule == "generic_user"


def test_goal_person_location_and_navigation():
    c = _ans("Where is the child?")
    assert (c.text, c.rule) == ("Child is at the bed.", "person_location")
    assert _ans("아이는 어디에 있어요?", "ko").text == "아이는 침대에 있어요."
    nav = {"all": [{"any": [{"pred": "robot_at", "args": ["bed@bedroom"]},
                            {"pred": "robot_at", "args": ["shelf@bedroom"]}]}]}
    c = _ans("Which place do you mean: bed in the bedroom or shelf in the bedroom or floor in the living room?",
             wants=nav)
    assert c.text == "The bed."
    assert _ans("I will go to the shelf in the bedroom. Is that right?", wants=nav).kind == "yes"
    assert _ans("I will go to the counter. Is that right?", wants=nav).text == "No, go to the bed."


def test_goal_rules_are_off_without_a_goal():
    w = FakeWorld()
    # a destination question is not read as "where is it?" (the user does not know what was asked)
    assert compose("Where should I put the blue mug?", "en", None, w, knows_location=True).rule == "generic_user"
    assert compose("Where is the blue mug?", "en", None, w, knows_location=True).text == "It's on the counter."


def test_goal_more_question_forms():
    assert _ans("Could you clarify where you want the blue mug placed?").text == "On the sink, please."
    assert _ans("Which place do you mean for the blue mug?").text == "On the sink, please."
    assert _ans("What should I do with the phone?").text == "Bring it to me, please."
    assert _ans("휴대폰은 어떻게 해야 할까요?", "ko").text == "저한테 갖다 주세요."
    # offered places that are not where the request goes: the user says who it is for
    c = _ans("Which place do you mean: counter in the kitchen or table in the living?",
             wants={"all": [{"pred": "held_by", "args": ["phone_1", "grandma"]}]})
    assert c.text == "Bring it to me, please."
    c = _ans("Which place do you mean: counter in the kitchen or table in the living?",
             wants={"all": [{"pred": "said_to", "args": ["child", "dinner_ready"]}]})
    assert c.text == "Child is at the bed."
    w = FakeWorld()
    c = compose("Which place should I look for the blue mug?", "en", None, w, knows_location=True)
    assert c.text == "It's on the counter."


def test_which_place_to_look_is_a_location_question():
    c = _ans("Which place should I look for the blue mug and the phone?")
    assert c.rule == "location" and c.text == "It's on the counter."


def test_goal_destination_without_the_object():
    one = {"all": [{"pred": "held_by", "args": ["phone_1", "grandma"]}]}
    assert _ans("여기 있어요? 어디에 가져다줘야 할까요?", "ko", wants=one).text == "저한테 갖다 주세요."
    assert _ans("Where should I put it?", wants=one).text == "Bring it to me, please."
    # an empty slot is not a question a person can place; two things going to different places: which one?
    assert _ans("Where should I put the ?", wants=one).rule != "goal_destination"
    assert _ans("Where should I put it?").rule != "goal_destination"


def test_question_followed_by_a_remark():
    assert classify("파란 책은 안락의자에요, 아니면 TV대에요? 두 곳에 동시에 놓을 수는 없어요.") == "yes_no"
    assert classify("Is it the red one? I can see two.") == "yes_no"
    c = _ans("파란 머그컵은 조리대에요, 아니면 싱크대에요? 두 곳에 놓을 수는 없어요.", "ko")
    assert c.text == "싱크대 위에 놔 주세요."
