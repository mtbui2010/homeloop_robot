"""r12 / r13 simulator freeze, user-side part (S7, S8; see test_dialog_r13_freeze.py):
two consistency fixes found by the per-task analysis of the n=50 gate. Worlds: the gate tasks' houses and start
states. No rate or scoring value changed."""
import pytest

from homeloop_robot.episode import make_episode
from helpers import patched


def _ep(house, seed_state, L, goal, request, profile="ideal", seed=0):
    ep = make_episode(house, seed_state, profile, seed, lang=L, user_spec={"persona": "adult"}, key="r13")
    ep.user.hear_instruction(request, L)
    ep.user.set_wants(goal)
    return ep


def _ask(ep, q, L, meaning=None):
    r, _h = ep.user.answer(q, L, tuple(ep.world.person_xy(ep.user.user_id)), 1.0, meaning=meaning)
    return r, ep.user.log[-1]


G033 = {"all": [{"pred": "on", "args": ["phone_1", "sofa@living"]}]}
G003 = {"all": [{"pred": "in", "args": ["milk_1", "kimchi_fridge@kitchen"]}]}


# ── S7: a wrong where-answer never names the true place ──────────────────────────────────────────────────────────
def test_s7_a_wrong_place_is_not_the_true_place():
    prof = patched("ideal", user__answer__p_wrong=1.0)
    n = 0
    for seed in range(60):
        ep = _ep("shared_flat", 9504, "en", G033, "Put the phone on the sofa.", profile=prof, seed=seed)
        r, log = _ask(ep, "Where is the phone?", "en")
        if log["kind"] != "wrong":
            continue
        n += 1
        true = ep.world.objects["phone_1"].at
        place = ep.world.house.places[true].name["en"]
        assert place not in r.text, (seed, r.text, true)
    assert n >= 30


# ── S8: a compound question gets both answers ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("L,q,where,dest", [
    ("en", "Where is the milk, and where would you like me to put it away?", "dining table", "kimchi fridge"),
    ("en", "Where is the milk, and where should I put it?", "dining table", "kimchi fridge"),
    ("ko", "우유는 어디에 있고, 어디에 넣어 둘까요?", "식탁", "김치냉장고")])
def test_s8_where_is_and_where_to_put_is_answered_in_both_parts(L, q, where, dest):
    ep = _ep("korean_apt_59", 7132, L, G003, {"en": "I'd like you to put the milk away.", "ko": "우유를 넣어 둘래요?"}[L])
    ep.user.p_location_unknown = 0.0
    r, log = _ask(ep, q, L)
    assert where in r.text and dest in r.text, (r.text, log)


def test_s8_where_is_alone_does_not_give_the_destination():
    ep = _ep("korean_apt_59", 7132, "en", G003, "I'd like you to put the milk away.")
    ep.user.p_location_unknown = 0.0
    r, log = _ask(ep, "Where is the milk?", "en")
    assert "kimchi" not in r.text, (r.text, log)
