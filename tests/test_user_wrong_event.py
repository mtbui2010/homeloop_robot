"""A wrong user reply (user.answer.p_wrong draw) is an injected user error: the ask call stays ok and carries the event
``user_wrong_answer`` in its truth, so the episode record can count it (homeloop_bench metrics.failure_events)."""
from helpers import patched
from homeloop_robot.episode import make_episode
from test_dialog_structured import GLASS_SPEC, HOUSE

Q = "Which mug do you mean: the white mug or the green mug?"


def _ask(p_wrong, seed=0):
    prof = patched("ideal", **{"user.answer.p_wrong": p_wrong})
    ep = make_episode(HOUSE, 0, prof, seed, lang="en", user_spec=GLASS_SPEC, key="wrong-event")
    return ep.robot.call("ask", question=Q, lang="en")


def test_a_wrong_reply_names_its_event_and_the_call_stays_ok():
    r = _ask(1.0)
    assert r.ok and (r.truth or {}).get("reply_kind") == "wrong"
    assert r.truth["event"] == "user_wrong_answer" and r.injected is False


def test_a_correct_reply_has_no_event():
    r = _ask(0.0)
    assert r.ok and (r.truth or {}).get("reply_kind") == "correct" and "event" not in r.truth
