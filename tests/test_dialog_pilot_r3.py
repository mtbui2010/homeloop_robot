"""Pilot round 3 (homeloop_bench docs/experiments.md "Pilot rounds"), hl-dev-000003 KO: SAGE's remark on what is
not in its plan ("(the 김치냉장고 you mentioned is not in my plan)") came out of the 8B translation as a question
('김치냉장고 얘기가 제 계획에 없나요?'). The rules took that remark for the question that is answered (the first
question, convention 2), saw only the kimchi fridge in it and said "yes" to a read-back that puts the milk in the
plain fridge. A remark is context: the read-back after it is what the user answers."""
import pytest

import test_dialog_structured as T
from homeloop_robot import intent

GOAL = {"all": [{"pred": "in", "args": ["milk_1", "kimchi_fridge@kitchen"]}]}
REQ = {"en": "I'd like you to put the milk away.", "ko": "우유를 넣어 둘래요?"}
SPEC = dict(T.MILK_SPEC, answer={"en": "In the kimchi fridge, please.", "ko": "김치냉장고요."})
EN_GOAL = "I will put the 우유 on the fridge in the kitchen."
HEARD = "김치냉장고 얘기가 제 계획에 없나요? 제가 우유를 주방 냉장고에 두겠습니다. 맞죠?"


def _ask(heard, meaning):
    ep, u = T._user("ko", SPEC, GOAL, REQ)
    r, _h = u.answer(heard, "ko", tuple(ep.world.people[ep.world.user_id()].pos), 1.0, meaning=meaning)
    return r, u.log[-1]


@pytest.mark.parametrize("meaning", [{"qtype": "confirm", "goal": EN_GOAL}, None])
def test_wrong_read_back_after_a_remark_question_is_corrected(meaning):
    r, log = _ask(HEARD, meaning)
    assert r.kind != "yes", (r.kind, r.text, log)
    assert "김치냉장고" in r.text, (r.text, log)


@pytest.mark.parametrize("meaning", [{"qtype": "confirm", "goal": "I will put the 우유 in the kimchi fridge in the "
                                                                   "kitchen."}, None])
def test_right_read_back_after_a_remark_question_is_confirmed(meaning):
    r, log = _ask("냉장고 얘기가 제 계획에 없나요? 제가 우유를 주방 김치냉장고에 두겠습니다. 맞죠?", meaning)
    assert r.kind == "yes", (r.kind, r.text, log)


def test_first_question_skips_a_remark_question():
    assert intent.text_for_rules(HEARD, "ko") == "제가 우유를 주방 냉장고에 두겠습니다. 맞죠?"
    en = "Is the counter you mentioned not in my plan? I will put the cup on the table. Is that right?"
    assert intent.text_for_rules(en, "en") == "I will put the cup on the table. Is that right?"
    # a remark-like question with no question after it is still the question
    assert intent.text_for_rules("김치냉장고 얘기가 제 계획에 없나요?", "ko") == "김치냉장고 얘기가 제 계획에 없나요?"
    # an ordinary first question still wins over a later one
    q = "어디에 둘까요? 냉장고 맞죠?"
    assert intent.text_for_rules(q, "ko") == "어디에 둘까요?"
