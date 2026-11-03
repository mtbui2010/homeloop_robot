"""A read-back behind SAGE's remark on what it did not understand ("I am not sure I understood (the TV stand you
mentioned is not in my plan). I will put the remote on the sofa. Is that right?"): the places and things named
in the remark are not part of the plan read back, so a wrong read-back is not confirmed (review round 1)."""
import pytest

from homeloop_robot import dialog as D
from test_dialog_structured import _ask

REMOTE_GOAL = {"all": [{"pred": "on", "args": ["remote_1", "tv_stand@living"]}]}
REMOTE_REQ = {"en": "Put the remote on the TV stand.", "ko": "리모컨 티비장 위에 놔 주세요."}

WRONG = {
    "en": ["I am not sure I understood (the TV stand you mentioned is not in my plan). I will put the remote on the "
           "sofa. Is that right?",
           "I am not sure I understood (you did not say the TV stand). I will put the remote on the sofa. "
           "Is that right?"],
    "ko": ["아, 제가 잘 이해한 건지 모르겠어요. (당신이 말한 '티비장'은 제 계획에 없어요.) 리모컨을 소파 위에 놓을게요. 맞죠?",
           "티비장 얘기한 거 제가 계획에 없어요. 리모컨을 소파에 둘게요. 맞죠?",
           "저는 이해했는지 확신이 안 돼요 (티비장은 제가 계획에 없어요). 리모컨을 소파에 둘게요. 맞죠?",
           "티비장, 소파... 모두 제가 계획에 포함된 건 아니에요. 리모컨을 소파에 둘게요. 맞죠?"],
}
RIGHT = {"en": "I am not sure I understood (the sofa you mentioned is not in my plan). I will put the remote on the "
               "TV stand. Is that right?",
         "ko": "(당신이 말한 '소파'는 제 계획에 없어요.) 리모컨을 티비장 위에 놓을게요. 맞죠?"}


@pytest.mark.parametrize("L,q", [(L, q) for L in ("en", "ko") for q in WRONG[L]])
def test_wrong_read_back_behind_the_remark_is_not_confirmed(L, q):
    r, log = _ask(L, q, None, goal=REMOTE_GOAL, req=REMOTE_REQ)
    assert r.kind == "no" and log["why"] == "goal_correct", (r.text, log)
    assert {"en": "TV stand", "ko": "티비장"}[L] in r.text


@pytest.mark.parametrize("L,q", [(L, q) for L in ("en", "ko") for q in WRONG[L][:1]])
def test_wrong_read_back_behind_the_remark_by_meaning(L, q):
    """The same read-back as SAGE's structured confirm (the adapter's goal slot): still "no"."""
    goal = "I will put the remote on the sofa."
    r, log = _ask(L, q, {"qtype": "confirm", "goal": goal}, goal=REMOTE_GOAL, req=REMOTE_REQ)
    assert r.kind == "no", (r.text, log)


@pytest.mark.parametrize("L", ["en", "ko"])
def test_right_read_back_behind_the_remark_is_confirmed(L):
    r, log = _ask(L, RIGHT[L], None, goal=REMOTE_GOAL, req=REMOTE_REQ)
    assert r.kind == "yes" and log["why"] == "goal_confirm", (r.text, log)


def test_strip_plan_remarks():
    assert D.strip_plan_remarks(WRONG["en"][0]) == "I will put the remote on the sofa. Is that right?"
    assert D.strip_plan_remarks(WRONG["ko"][1]) == "리모컨을 소파에 둘게요. 맞죠?"
    # a plain read-back and a parenthetical that is not a remark stay
    plain = "I will put the remote (the black one) on the sofa. Is that right?"
    assert D.strip_plan_remarks(plain) == plain
    assert D.strip_plan_remarks("Is that right?") == "Is that right?"
