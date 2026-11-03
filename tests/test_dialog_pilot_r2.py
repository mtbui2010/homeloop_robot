"""Pilot round 2 (homeloop_bench docs/experiments.md "Pilot rounds"), hl-dev-000013 KO: a read-back of a message
is judged for who tells whom and for the message itself. '남편이 “...”라고 말하는 거죠?' ("your husband is the one
saying it?") reverses the roles and is corrected, in the structured path (sage) and in free text (sage_norag), where
it was read as a check of a heard word ("Did you mean ...?") and answered "yes"."""
import pytest

import test_dialog_structured as T
from homeloop_robot import dialog as D
from homeloop_robot.world import from_house

GOAL = {"all": [{"pred": "said_to", "args": ["partner_b", "leaving_soon"]}]}
REQ = {"en": "Let my husband know we're leaving in ten minutes, please.", "ko": "남편한테 가서 10분 있다가 나간다고 말해 주세요."}
EN = "I will say \"10분 있다가 나간다고 말해 주세요.\" in the husband."
SAGE_KO = "아, 제가 그 부분을 제대로 이해한 건지 모르겠어요. 남편이 “10분 있다가 나간다고 말해 주세요”라고 말하는 거죠? 맞죠?"
NORAG_KO = "아, 제가 이해한 게 맞는지 확신이 안 돼요. 남편이 “10분 있다가 나간다고 말해 주세요”라고 말할 거예요, 맞죠?"


def _ask(L, heard, meaning, monkeypatch):
    monkeypatch.setattr(T, "HOUSE", "couple_flat")
    ep, u = T._user(L, {"persona": "adult"}, GOAL, REQ)
    r, _h = u.answer(heard, L, tuple(ep.world.people[ep.world.user_id()].pos), 1.0, meaning=meaning)
    return r, u.log[-1]


@pytest.mark.parametrize("q,role", [
    ("남편이 “10분 있다가 나간다고”라고 말하는 거죠?", "speaker"),
    ("남편한테 “10분 있다가 나간다고”라고 전할게요. 맞죠?", "listener"),
    ("남편에게 10분 있다가 나간다고 말할게요.", "listener"),
    ("Your husband will say \"we're leaving in ten minutes\"?", "speaker"),
    ("I will say \"We're leaving in ten minutes.\" to husband.", "listener"),
    ("I'll tell your husband that we're leaving in ten minutes.", "listener"),
    ("“남편이 온대요”라고 말할게요.", None),                       # a name inside the quote is not a role
])
def test_speech_role(q, role):
    assert D.speech_role(from_house("couple_flat", 0), "partner_b", q) == role


@pytest.mark.parametrize("q,meaning", [(SAGE_KO, {"qtype": "confirm", "goal": EN}), (SAGE_KO, None),
                                       (NORAG_KO, None)])
def test_reversed_roles_are_corrected(q, meaning, monkeypatch):
    r, log = _ask("ko", q, meaning, monkeypatch)
    assert r.kind == "no" and log.get("why") != "repair_confirm", (r.kind, r.text, log)


@pytest.mark.parametrize("q", ["남편에게 “10분 있다가 나간다고 합니다.”라고 말할게요. 맞죠?",
                               "남편한테 10분 있다가 나간다고 전할게요. 맞죠?"])
def test_right_read_back_is_confirmed(q, monkeypatch):
    r, _log = _ask("ko", q, None, monkeypatch)
    assert r.kind == "yes", (r.kind, r.text)


def test_wrong_message_is_corrected(monkeypatch):
    g = "I will say \"Dinner is ready.\" to husband."
    r, _log = _ask("en", g + " Is that right?", {"qtype": "confirm", "goal": g}, monkeypatch)
    assert r.kind == "no", r.text
    g = "I will say \"We're leaving in ten minutes.\" to husband."
    r, _log = _ask("en", g + " Is that right?", {"qtype": "confirm", "goal": g}, monkeypatch)
    assert r.kind == "yes", r.text


def test_heard_word_check_still_answered_yes(monkeypatch):
    # a check of a heard word is still a repair question (no person named in a role, no "will say")
    r, log = _ask("ko", "'나간다고'라고 말씀하신 거 맞죠?", None, monkeypatch)
    assert r.kind == "yes" and log.get("why") == "repair_confirm", (r.text, log)
