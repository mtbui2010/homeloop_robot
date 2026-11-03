"""Pilot round 1 (docs: homeloop_bench docs/experiments.md "Pilot rounds"), hl-dev-000010 / 000013:
- a read-back of a delivery to the speaker is confirmed when it names the speaker as "you", by their own name or
  by their place, and still not by a raw id or by another person;
- a structured confirm is answered for the sentence the user heard: a Korean translation that drops or changes the
  destination / person is corrected (path structured_mismatch), even when the English meaning was right;
- SAGE's joined questions with an empty slot do not leak the next question into the slot."""
import pytest

import test_dialog_structured as T
from homeloop_robot.configs.ra_dialog import derive

MUG_GOAL = {"all": [{"pred": "delivered", "args": ["mug_2", "user"], "mode": "reach", "mode_reason": None}]}
MUG_REQ = {"en": "Hey, can you grab me that green mug and put it over here?", "ko": "초록색 머그컵 좀 가져와 주실래요?"}
SRC = "from the counter in the kitchen "


def _confirm(L, heard, goal_en, house="korean_apt_59", goal=MUG_GOAL, req=MUG_REQ, monkeypatch=None):
    monkeypatch.setattr(T, "HOUSE", house)
    ep, u = T._user(L, {"persona": "adult"}, goal, req)
    r, _h = u.answer(heard, L, tuple(ep.world.people[ep.world.user_id()].pos), 1.0,
                     meaning={"qtype": "confirm", "goal": goal_en})
    return r, u.log[-1]


@pytest.mark.parametrize("dest,ok", [("the spot near you", True), ("the user", True), ("you", True),
                                     ("the person_user", False), ("the grandpa", False)])
def test_read_back_to_the_speaker(dest, ok, monkeypatch):
    g = f"I will put the green mug {SRC}on {dest}."
    r, log = _confirm("en", g + " Is that right?", g, monkeypatch=monkeypatch)
    assert log["path"] == "structured"
    assert r.kind == ("yes" if ok else "no"), (dest, r.text)


def test_read_back_to_another_person_by_name(monkeypatch):
    goal = {"all": [{"pred": "said_to", "args": ["partner_b", "leaving_soon"]}]}
    req = {"en": "Go tell my husband we're leaving in ten minutes.", "ko": "남편한테 가서 10분 있다가 나간다고 말해 주세요."}
    for who, kind in (("husband", "yes"), ("partner_b", "no")):
        g = f"I will say \"We're leaving in ten minutes.\" to {who}."
        r, _log = _confirm("en", g + " Is that right?", g, "couple_flat", goal, req, monkeypatch)
        assert r.kind == kind, (who, r.text)


def test_korean_read_back_answered_for_what_was_heard(monkeypatch):
    # the English meaning is right ("on you"); the Korean the user hears puts the mug in the kitchen
    r, log = _confirm("ko", "카운터에 있는 녹색 머그잔을 주방에 놓겠습니다. 맞죠?",
                      f"I will put the green mug {SRC}on you.", monkeypatch=monkeypatch)
    assert r.kind == "no" and log["path"] == "structured_mismatch", (r.text, log)
    r, log = _confirm("ko", "녹색 머그잔을 당신 근처 자리에 놓겠습니다. 맞죠?",
                      f"I will put the green mug {SRC}on the spot near you.", monkeypatch=monkeypatch)
    assert r.kind == "yes" and log["path"] == "structured", (r.text, log)


def test_korean_read_back_with_a_raw_id_for_the_person(monkeypatch):
    goal = {"all": [{"pred": "said_to", "args": ["partner_b", "leaving_soon"]}]}
    req = {"en": "Go tell my husband we're leaving in ten minutes.", "ko": "남편한테 가서 10분 있다가 나간다고 말해 주세요."}
    en = "I will say \"10분 있다가 나간다고 합니다.\" to husband."
    r, log = _confirm("ko", "파트너B에게 \"10분 있다가 나간다고 합니다.\"라고 말할게요. 맞죠?", en, "couple_flat", goal, req,
                      monkeypatch)
    assert r.kind == "no" and log["path"] == "structured_mismatch", (r.text, log)
    r, log = _confirm("ko", "남편에게 \"10분 있다가 나간다고 합니다.\"라고 말할게요. 맞죠?", en, "couple_flat", goal, req,
                      monkeypatch)
    assert r.kind == "yes" and log["path"] == "structured", (r.text, log)


def test_empty_slot_does_not_swallow_the_next_question():
    d = derive("Where should I put the ? Where should I put the green mug?")
    assert d["qtype"] == "which_place" and d["obj"] == "green mug", d
    d = derive("I couldn't find the ? Where is it? Where should I put the cup?")
    assert "?" not in str(d.get("obj", "")), d
