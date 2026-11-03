"""ASR repair questions, English and Korean (R2-5 B3, docs/user_model.md): "Did you mean X?" about the user's own
words, "could you repeat?", and a plain Korean "어디(에) 있어요?" read as "where are you?"."""
import collections

import pytest

from homeloop_robot.dialog import GoalView, compose
from homeloop_robot.episode import make_episode
from homeloop_robot.world import from_house

HOUSE = "korean_apt_59"
REQ = {"en": "Could you put the apple in the fridge, and while you're in the kitchen, bring me the white mug? "
             "I'd like the white mug right in my hand.",
       "ko": "사과 좀 냉장고에 넣어 두고, 주방에 간 김에 하얀 머그컵 좀 갖다줘요. 하얀 머그컵은 제 손에 바로 건네주세요."}
WANTS = {"all": [{"pred": "in", "args": ["apple_1", "fridge@kitchen"]},
                 {"pred": "delivered", "args": ["mug_1", "user"], "mode": "hand", "mode_reason": "explicit"}]}


def _compose(q, L, last=None, request=True):
    w = from_house(HOUSE, 0)
    gv = GoalView(w, WANTS, "user", lambda pid: "sofa@living")
    return compose(q, L, {"persona": "adult"}, w, knows_location=True, user_place=("sofa@living", False), goal=gv,
                   request=REQ[L] if request else None, last_answer=last)


@pytest.mark.parametrize("L,q", [
    ("en", "Do you mean 'while you're in the kitchen'? Or was 'chicken' a typo?"),
    ("en", "Did you mean 'while you're in the kitchen'? And what do you mean by 'my hard'?"),
    ("en", "Did you say the white mug?"),
    ("ko", "'주방에 간 김에'라고 하셨어요?"),
    ("ko", "하얀 머그컵 말씀이세요?"),
    ("ko", "'주방'이 맞나요? 아니면 오타인가요?"),
])
def test_did_you_mean_own_words_is_yes_and_restates(L, q):
    c = _compose(q, L)
    assert c.rule == "repair_confirm" and c.kind == "yes" and c.informative
    assert c.text == {"en": "Yes. ", "ko": "네. "}[L] + REQ[L]


@pytest.mark.parametrize("L,q", [
    ("en", "Did you mean 'chicken'?"),                  # not a word of the request
    ("en", "Did you mean the blue bowl?"),              # another object: answered from the goal, not a repair
    ("ko", "'치킨'이라고 하셨어요?"),
])
def test_did_you_mean_other_words_is_not_a_repair_yes(L, q):
    c = _compose(q, L)
    assert c.rule != "repair_confirm"


def test_no_request_known_no_repair():
    assert _compose("Did you mean 'while you're in the kitchen'?", "en", request=False).rule != "repair_confirm"


@pytest.mark.parametrize("L,q", [
    ("en", "Sorry, could you repeat that?"),
    ("en", "I didn't catch that. Could you say it again?"),
    ("ko", "죄송해요, 다시 한 번 말씀해 주시겠어요?"),
    ("ko", "뭐라고 하셨어요?"),
])
def test_repeat_gives_the_original_request(L, q):
    c = _compose(q, L)
    assert c.rule == "repeat_request" and c.text == REQ[L] and not c.informative


@pytest.mark.parametrize("L,q,last", [
    ("en", "Sorry, could you repeat that?", "On the coffee table, please."),
    ("ko", "다시 말씀해 주시겠어요?", "커피 테이블 위에 놔 주세요."),
])
def test_repeat_after_an_answer_repeats_the_answer(L, q, last):
    c = _compose(q, L, last=last)
    assert c.rule == "repeat_answer" and c.text == last


def test_repeat_naming_the_request_gives_the_request_even_after_an_answer():
    c = _compose("Could you repeat what you'd like me to do?", "en", last="On the coffee table, please.")
    assert c.rule == "repeat_request" and c.text == REQ["en"]


@pytest.mark.parametrize("q", ["어디에 있어요?", "지금 어디 있어요?", "죄송한데 어디에 있어요?"])
def test_plain_korean_where_is_where_are_you(q):
    c = _compose(q, "ko")
    assert c.rule == "self_position" and "소파" in c.text


@pytest.mark.parametrize("q", ["사과는 어디에 있어요?", "할아버지는 어디에 있어요?"])
def test_korean_where_is_something_is_not_where_are_you(q):
    assert _compose(q, "ko").rule != "self_position"


@pytest.mark.parametrize("L", ["en", "ko"])
def test_repair_through_the_user_model_keeps_the_mix_and_asr(L):
    """Through SimUser.answer (profile real): the no-answer / not-sure mix still applies to repair questions, and a
    repeated request goes through ASR again."""
    q_mean = {"en": "Did you mean 'while you're in the kitchen'?", "ko": "'주방에 간 김에'라고 하셨어요?"}[L]
    q_rep = {"en": "Sorry, could you repeat that?", "ko": "다시 한 번 말씀해 주시겠어요?"}[L]
    kinds = collections.Counter()
    heard_diff = 0
    for seed in range(200):
        ep = make_episode(HOUSE, 0, "real", seed, lang=L, key=f"repair|{seed}")
        u = ep.user
        u.hear_instruction(REQ[L], L)
        u.set_wants(WANTS)
        xy = ep.world.robot.pose[:2]
        r, h = u.answer(q_mean, L, xy, 1.0)
        kinds[r.kind] += 1
        r2, h2 = u.answer(q_rep, L, xy, 5.0)
        if r2.kind != "no_answer":
            # the second question follows an answer only when the first was informative
            assert r2.text in (REQ[L], r.text)
            heard_diff += h2.text != r2.text
    assert kinds["yes"] > 100 and kinds["no_answer"] + kinds["not_sure"] > 0
    assert heard_diff > 0
