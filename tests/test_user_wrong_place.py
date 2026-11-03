"""Pilot round 2 (hl-dev-000010 KO): a mistaken "where" answer names a place where an object of the task is
usually kept (catalog typical receptacle, realism R-b), not any surface or container of the house ("옷장 안에 넣어
주세요" for a mug the user wants to drink tea from)."""
import pytest

import test_dialog_structured as T
from homeloop_robot.catalog import is_typical, place_category, size_fits
from homeloop_robot.houses import list_houses

MUG_GOAL = {"all": [{"pred": "delivered", "args": ["mug_2", "user"], "mode": "reach", "mode_reason": None}]}
MUG_REQ = {"en": "Hey, can you grab me that green mug and put it over here?", "ko": "초록색 머그컵 좀 가져와 주실래요?"}


def test_wrong_places_are_usual_places_of_the_object(monkeypatch):
    monkeypatch.setattr(T, "HOUSE", "korean_apt_59")
    ep, u = T._user("ko", {"persona": "adult"}, MUG_GOAL, MUG_REQ)
    w = ep.world
    got = u.wrong_places()
    assert got and all(is_typical("mug", place_category(w.house.places[p])) for p in got), got
    assert not any(p.startswith(("wardrobe", "closet", "shoe")) for p in got), got


def test_wrong_destination_answer_is_a_usual_place(monkeypatch):
    monkeypatch.setattr(T, "HOUSE", "korean_apt_59")
    seen = set()
    for seed in range(40):
        ep, u = T._user("ko", {"persona": "adult"}, MUG_GOAL, MUG_REQ, profile="real", seed=seed)
        r, _h = u.answer("녹색 머그잔을 제가 가져다드릴까요, 아니면 근처에 놓을까요?", "ko",
                         tuple(ep.world.people[ep.world.user_id()].pos), 1.0)
        if r.kind == "wrong":
            seen.add(r.text)
    assert seen, "no wrong draw in 40 seeds"
    assert not any("옷장" in t or "신발장" in t for t in seen), seen


@pytest.mark.parametrize("house", list_houses())
def test_no_task_object_falls_back_to_every_place(house, monkeypatch):
    monkeypatch.setattr(T, "HOUSE", house)
    ep, u = T._user("en", {"persona": "adult"}, {"all": [{"pred": "docked", "args": []}]}, {"en": "Go charge.",
                                                                                           "ko": "충전하러 가세요."})
    w = ep.world
    assert u.wrong_places() == sorted(p for p, pl in w.house.places.items() if pl.kind in ("surface", "container"))
    # every object class of the house has at least one usual place to be confused with
    for o in w.objects.values():
        assert any(is_typical(o.cls, place_category(pl)) and size_fits(o.cls, place_category(pl))
                   for pl in w.house.places.values() if pl.kind in ("surface", "container")), (house, o.cls)
