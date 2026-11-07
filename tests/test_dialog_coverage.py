"""The coverage question ("You also asked me for this, but I have not done it: <part>. Should I do it now?", SAGE's
request_coverage): structured confirm with ask=coverage, the part as the goal slot. The user answers from the TRUE state:
yes when something the part is about does not hold, no when all of it holds, not sure when the part is about nothing the
user asked; the text the user hears (EN, and the robot's KO phrase) must read as the same question (heard-text check)."""
import pytest

from homeloop_robot import intent
from homeloop_robot.configs.ra_dialog import derive
from homeloop_robot.episode import make_episode
from test_dialog_structured import FETCH_GOAL, FETCH_REQ, HOUSE, _ask

PART = {"en": "put the remote on the TV stand", "ko": "리모컨을 TV대 위에 놓아 주세요"}
QUESTION = {"en": "You also asked me for this, but I have not done it: {p}. Should I do it now?",
            "ko": "\"{p}\"도 부탁하셨는데 아직 못 했어요. 지금 할까요?"}


def _q(L, part=None):
    return QUESTION[L].format(p=part or PART[L])


def _meaning(L, part=None):
    return {k: v for k, v in derive(QUESTION["en"].format(p=part or PART[L])).items() if k != "template"}


def test_clean_keeps_ask_coverage_only():
    assert intent.clean({"qtype": "confirm", "goal": "x", "ask": "coverage"}) == {"qtype": "confirm", "goal": "x", "ask": "coverage"}
    assert "ask" not in intent.clean({"qtype": "confirm", "goal": "x", "ask": "bogus"})


@pytest.mark.parametrize("L", ["en", "ko"])
def test_the_text_reads_as_the_coverage_question(L):
    assert intent.read_coverage(_q(L), L) == {"qtype": "confirm", "ask": "coverage", "goal": PART[L]}
    assert intent.read_coverage("Should I do it now?", L) is None


@pytest.mark.parametrize("L", ["en", "ko"])
def test_a_part_not_done_gets_yes(L):
    r, log = _ask(L, _q(L), _meaning(L))
    assert r.kind == "yes" and log["why"] == "coverage" and log["path"] == "structured" and log["qtype"] == "confirm", (r.text, log)


@pytest.mark.parametrize("L", ["en", "ko"])
def test_a_part_that_holds_gets_no(L):
    ep = make_episode(HOUSE, 0, "ideal", 0, lang=L, user_spec={"persona": "adult"}, key="coverage|holds")
    u = ep.user
    u.hear_instruction(FETCH_REQ[L], L)
    u.set_wants({"all": [{"pred": "robot_at", "args": [next(iter(ep.world.house.places))]}] + FETCH_GOAL["all"]})
    w = ep.world
    for a in u.wants["all"]:                      # put the world in the state the request asked for
        if a["pred"] == "on":
            w.objects[a["args"][0]].at = a["args"][1]
            w.objects[a["args"][0]].inside = False
    r, _h = u.answer(_q(L), L, tuple(w.people["user"].pos), 1.0, meaning=_meaning(L))
    assert r.kind == "no" and u.log[-1]["why"] == "coverage", (r.text, u.log[-1])


@pytest.mark.parametrize("L", ["en", "ko"])
def test_a_part_about_nothing_asked_is_not_understood(L):
    part = {"en": "water the plants", "ko": "화분에 물 주세요"}[L]
    r, log = _ask(L, _q(L, part), _meaning(L, part))
    assert r.kind == "not_sure", (r.text, log)


def test_a_korean_phrase_that_lost_the_question_is_answered_as_heard():
    """The meaning says coverage, but the text the user hears is not that question (a translation that dropped it): the
    user answers what they heard (structured_mismatch)."""
    m = _meaning("ko")
    r, log = _ask("ko", "리모컨 어디에 둘까요?", m)
    assert log["path"] == "structured_mismatch", (r.text, log)


def test_untranslated_english_is_not_followed_by_a_korean_user():
    r, log = _ask("ko", _q("en"), _meaning("en"))
    assert log["path"] == "structured_mismatch" and log["why"] == "not_in_lang", log
