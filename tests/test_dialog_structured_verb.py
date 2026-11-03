"""robot_agent's verb issue ("What should I open?" / "What should I close?", understand.issue_question with the
verbs of understand._VERB) asks which container or door: a which_place meaning with the verb kept as a slot, and
the user answers with the container the request opens / closes (review round 1). The free-text rules read the
same question the same way, in English and Korean."""
import pytest

from homeloop_robot import intent
from homeloop_robot.configs.ra_dialog import derive
from homeloop_robot.episode import make_episode

HOUSE = "shared_flat"
# the goals of dev tasks hl-dev-000001 / -000026 ("open the fridge and put the plate in") and hl-dev-000000 /
# -000028 ("open the microwave")
FRIDGE = ({"all": [{"pred": "open", "args": ["fridge@kitchen"]}, {"pred": "in", "args": ["plate_1", "fridge@kitchen"]}]},
          {"en": "Open the fridge and put the plate inside.", "ko": "냉장고 좀 열어 주시고, 접시를 안쪽에 정리해 주세요."},
          {"en": "The fridge.", "ko": "냉장고요."})
MICRO = ({"all": [{"pred": "open", "args": ["microwave@kitchen"]}]},
         {"en": "Could you open the microwave?", "ko": "전자레인지 문 좀 열어 주시겠어요?"},
         {"en": "The microwave.", "ko": "전자레인지요."})
QUESTION = {"en": "What should I open?", "ko": "뭘 열까요?"}


def _ask(L, q, meaning, goal, req):
    ep = make_episode(HOUSE, 0, "ideal", 0, lang=L, user_spec={"persona": "adult"}, key="verb")
    u = ep.user
    u.hear_instruction(req[L], L)
    u.set_wants(goal)
    r, _h = u.answer(q, L, tuple(ep.world.people[u.user_id].pos), 1.0, meaning=meaning)
    return r, u.log[-1]


@pytest.mark.parametrize("L", ["en", "ko"])
@pytest.mark.parametrize("task", [FRIDGE, MICRO], ids=["fridge_plate", "microwave"])
def test_what_should_i_open_is_the_container(L, task):
    goal, req, answer = task
    m = derive("What should I open?")
    assert m["qtype"] == "which_place" and m["verb"] == "open"
    r, log = _ask(L, QUESTION[L], m, goal, req)
    assert log["path"] == "structured" and r.text == answer[L] and log["why"] == "goal_place", (r.text, log)
    # the same question as free text: the rules read it as the same meaning
    r, log = _ask(L, QUESTION[L], None, goal, req)
    assert log["path"] == "rules" and log["qtype"] == "which_place" and r.text == answer[L], (r.text, log)


def test_close_with_nothing_to_close_is_not_sure():
    goal, req, _a = MICRO
    r, log = _ask("en", "What should I close?", derive("What should I close?"), goal, req)
    assert r.kind == "not_sure"


@pytest.mark.parametrize("q,verb", [("What should I open?", "open"), ("What should I shut?", "close"),
                                    ("뭘 열까요?", "open"), ("무엇을 닫아야 하나요?", "close"), ("어떤 걸 열어 드릴까요?", "open")])
def test_free_rules_read_the_verb(q, verb):
    w = make_episode(HOUSE, 0, "ideal", 0).world
    m, rule = intent.read_free(q, "ko" if intent._hangul(q) else "en", w)
    assert m == {"qtype": "which_place", "verb": verb} and rule == "free_what_to_open"


def test_verb_slot_cleaned():
    assert intent.clean({"qtype": "which_place", "verb": "shut"}) == {"qtype": "which_place", "verb": "close"}
    assert intent.clean({"qtype": "which_place", "verb": "dance"}) == {"qtype": "which_place"}
