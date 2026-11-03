"""R2-6 H2: the simulated user matches names longest first. 냉장고 inside 김치냉장고 (and "fridge" inside "kimchi
fridge") names the kimchi fridge, not the fridge, so a correct read-back naming the kimchi fridge is confirmed
and does not trigger the clarification answer (sage run hl-dev-000041, KO). A modifier that the thing itself is
called by ("cup" in "red cup") still counts."""
import pytest

from homeloop_robot.dialog import GoalView, compose, mentions
from homeloop_robot.world import from_house

MILK_SPEC = {"persona": "adult", "slot": "destination", "intended": "kimchi_fridge@kitchen",
             "candidates": [{"id": "fridge@kitchen", "mentions": {"en": ["fridge", "refrigerator"], "ko": ["냉장고"]}},
                            {"id": "kimchi_fridge@kitchen", "mentions": {"en": ["kimchi fridge"],
                                                                         "ko": ["김치냉장고", "김치 냉장고"]}}],
             "answer": {"en": "In the kimchi fridge, please.", "ko": "김치냉장고요."}}
MILK_GOAL = {"all": [{"pred": "in", "args": ["milk_1", "kimchi_fridge@kitchen"]}]}
MILK_REQ = {"en": "Stash the milk carton.", "ko": "우유 좀 정리해 주실 수 있을까요?"}


def _ans(q, L, spec=MILK_SPEC, goal=MILK_GOAL):
    w = from_house("korean_apt_59", 0)
    gv = GoalView(w, goal, "user", lambda pid: None)
    return compose(q, L, spec, w, knows_location=True, user_place=(None, False), goal=gv, request=MILK_REQ[L],
                   last_answer=None)


@pytest.mark.parametrize("L,q", [
    ("ko", "차가운 우유를 부엌 김치냉장고에 넣을게요. 맞죠?"),        # the hl-dev-000041 read-back
    ("ko", "우유를 김치 냉장고에 넣을까요?"),
    ("en", "I'll put the cold milk in the kitchen kimchi fridge. Right?"),
    ("en", "Should I put the milk in the kimchi fridge?"),
])
def test_readback_naming_the_kimchi_fridge_is_confirmed(L, q):
    c = _ans(q, L)
    assert (c.kind, c.rule) == ("yes", "yes_no_intended"), c


@pytest.mark.parametrize("L,q", [("ko", "우유를 냉장고에 넣을게요. 맞죠?"),
                                 ("en", "I'll put the milk in the fridge. Right?")])
def test_readback_naming_the_plain_fridge_is_corrected(L, q):
    c = _ans(q, L)
    assert (c.kind, c.rule) == ("no", "yes_no_other"), c
    assert "kimchi fridge" in c.text.lower() if L == "en" else "김치냉장고" in c.text


@pytest.mark.parametrize("L,q", [("ko", "냉장고요, 아니면 김치냉장고요?"),
                                 ("en", "The fridge or the kimchi fridge?")])
def test_both_named_is_still_the_choice(L, q):
    assert _ans(q, L).rule == "clarify_answer"


def test_goal_readback_without_a_clarification():
    # no candidates: the goal read-back path (GoalView.covered) with a fridge and a kimchi fridge in the house
    yes = _ans("차가운 우유를 김치냉장고에 넣을게요. 맞죠?", "ko", spec={"persona": "adult"})
    assert (yes.kind, yes.rule) == ("yes", "goal_confirm"), yes
    no = _ans("우유를 냉장고에 넣을게요. 맞죠?", "ko", spec={"persona": "adult"})
    assert (no.kind, no.rule) == ("no", "goal_correct"), no


def test_mentions_longest_match():
    w = from_house("korean_apt_59", 0)
    assert mentions("김치냉장고에 넣을게요", "냉장고", "ko")                  # no world: plain substring
    assert not mentions("김치냉장고에 넣을게요", "냉장고", "ko", w)
    assert mentions("냉장고에 넣고 김치냉장고도 닫을게요", "냉장고", "ko", w)    # one free occurrence is enough
    assert not mentions("the kimchi fridge", "fridge", "en", w)
    assert mentions("the kimchi fridge", "kimchi fridge", "en", w)
    # a colour + class name of an object is still that class ("cup" in "red cup")
    cup = next(o for o in sorted(w.objects) if w.objects[o].cls in ("cup", "mug"))
    from homeloop_robot.dialog import object_names
    longest = object_names(w, cup, "en")[0]
    short = object_names(w, cup, "en")[-1]
    assert longest != short and mentions(f"the {longest}", short, "en", w)
