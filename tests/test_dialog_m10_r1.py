"""Milestone 10, round 1: the simulated user (docs/user_model.md).

* "Did you mean X?" about a word of the user's own LAST ANSWER is a yes, and the user says that answer again.
* A plan read-back on a task with no goal view (a refused request) is answered about the plan; the refusal script
  ("Oh, right. Never mind.") answers an explanation, not a read-back."""
from homeloop_robot.dialog import compose, is_plan_readback
from homeloop_robot.world import from_house

HOUSE = "korean_apt_59"
REQ = {"en": "Could you stash the bleach in the kimchi fridge? I'll handle it later.",
       "ko": "김치냉장고에 락스를 좀 넣어 주시겠어요? 나중에 정리하도록 할게요."}
SPEC = {"persona": "adult", "candidates": [],
        "answer": {"en": "Oh, right. Never mind then.", "ko": "아, 그렇네요. 그럼 됐어요."}}


def _w():
    return from_house(HOUSE, 0)


def _ask(q, L, request=REQ, spec=SPEC, last=None):
    return compose(q, L, spec, _w(), knows_location=True, user_place=("sofa@living", False), goal=None,
                   request=request[L], last_answer=last)


def test_readback_naming_the_object_of_the_request_is_yes():
    c = _ask("I will open the kimchi fridge, then put the bleach in the kimchi fridge. Is that right?", "en")
    assert c.rule == "plan_readback" and c.kind == "yes"
    c = _ask("김치냉장고 열게요, 그다음 락스 김치냉장고 안에 넣을게요. 맞아요?", "ko")
    assert c.rule == "plan_readback" and c.kind == "yes"


def test_readback_naming_another_object_is_no_and_the_request_again():
    c = _ask("I will open the kimchi fridge, then put the lysol in the kimchi fridge. Is that right?", "en")
    assert c.rule == "plan_readback" and c.kind == "no" and REQ["en"] in c.text
    c = _ask("김치냉장고 열게요, 그다음 리솔 김치냉장고 안에 넣을게요. 맞아요?", "ko")
    assert c.rule == "plan_readback" and c.kind == "no" and REQ["ko"] in c.text


def test_a_question_that_is_no_readback_still_gets_the_script():
    assert not is_plan_readback("That is not safe. Are you sure?")
    c = _ask("That is not safe. Are you sure?", "en")
    assert c.rule == "scripted_answer"


def test_did_you_mean_a_word_of_the_last_answer_is_yes():
    req = {"en": "Please bring me the towel.", "ko": "수건 좀 가져다 주세요."}
    last = {"en": "It might be in the master wardrobe.", "ko": "안방 옷장에 있을 거예요."}
    c = _ask("Did you mean 'wardrobe'?", "en", request=req, spec={"persona": "adult"}, last=last["en"])
    assert c.kind == "yes" and c.text.endswith(last["en"])
