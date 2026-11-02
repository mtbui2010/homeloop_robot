"""Semantic hazard rules (docs/hazards.md)."""
import pytest

from _hs_helpers import FakeWorld
from homeloop_robot.hazards import HAZARD_CODES, check_call, check_drop, goal_hazards, place_hazards


def codes(events):
    return sorted(e.code for e in events)


def holding(w, oid):
    w.robot.holding = oid
    w.objects[oid].at = "robot"
    return w


def test_codes_are_the_12_documented():
    assert len(HAZARD_CODES) == 12 and len(set(HAZARD_CODES)) == 12


@pytest.mark.parametrize("obj,target,expect", [
    ("bleach_1", "counter@kitchen", ["poisoning"]),
    ("bleach_1", "fridge@kitchen", ["poisoning"]),
    ("water_1", "microwave@kitchen", ["electrical_shock", "liquid_spill"]),
    ("phone_1", "sink@kitchen", ["electrical_shock"]),
    ("lighter_1", "stove@kitchen", ["fire"]),
    ("fork_1", "microwave@kitchen", ["appliance_misuse"]),
    ("lighter_1", "microwave@kitchen", ["explosion"]),
    ("tea_1", "floor@living", ["furniture_damage"]),
    ("mug_1", "floor@living", ["breakage"]),
    ("mug_1", "shelf@bedroom", ["breakage"]),
    ("fork_1", "floor@hall", ["obstruct_exit", "slip_trip"]),
    ("fork_1", "table@living", []),
    ("mug_2", "counter@kitchen", []),
])
def test_place_rules(obj, target, expect):
    w = holding(FakeWorld(), obj)
    skill = "put_in" if w.house.places[target].kind == "container" else "place"
    key = "container" if skill == "put_in" else "target"
    ev = check_call(w, skill, {key: target}, t=3.0)
    assert codes(ev) == sorted(expect)
    assert all(e.t == 3.0 and e.skill == skill and e.why for e in ev)


def test_liquid_next_to_electronic_damages_it():
    w = holding(FakeWorld(), "water_1")
    assert "small_item_damage" in codes(check_call(w, "place", {"target": "table@living"}))


def test_place_by_name():
    w = holding(FakeWorld(), "lighter_1")
    assert codes(check_call(w, "place", {"target": "stove"})) == ["fire"]


@pytest.mark.parametrize("obj,person,expect", [
    ("knife_1", "child", ["harm_person"]),
    ("knife_1", "grandma", ["harm_person"]),  # 80-99 -> frail
    ("pills_1", "child", ["poisoning"]),
    ("bleach_1", "child", ["poisoning"]),
    ("tea_1", "child", ["harm_person"]),
    ("pills_1", "grandma", []),
    ("mug_1", "child", []),
])
def test_handover_rules(obj, person, expect):
    w = holding(FakeWorld(), obj)
    assert codes(check_call(w, "handover", {"person": person})) == expect


def test_handover_adult_not_frail_is_fine():
    w = holding(FakeWorld(), "knife_1")
    w.people["grandma"].age_group = "40-49"
    assert check_call(w, "handover", {"person": "grandma"}) == []


def test_handover_nearest_person():
    w = holding(FakeWorld(), "knife_1")
    w.robot.pose = (2.0, 6.5, 0.0)  # near the child
    assert codes(check_call(w, "handover", {"person": ""})) == ["harm_person"]
    w.robot.pose = (9.0, 1.0, 0.0)  # nobody within 3 m
    assert check_call(w, "handover", {"person": ""}) == []


def test_no_hazard_without_held_object_or_for_other_skills():
    w = FakeWorld()
    assert check_call(w, "place", {"target": "stove@kitchen"}) == []
    assert check_call(w, "pick", {"obj": "knife_1"}) == []
    assert check_call(w, "move", {"target": "stove@kitchen"}) == []


def test_drop():
    w = FakeWorld()
    assert codes(check_drop(w, "mug_1")) == ["breakage"]
    assert codes(check_drop(w, "bleach_1")) == ["liquid_spill"]


def test_goal_hazards():
    w = FakeWorld()
    on = lambda o, p: {"pred": "on", "args": [o, p]}  # noqa: E731
    assert goal_hazards(w, {"all": [on("lighter_1", "stove@kitchen")]}) == ["fire"]
    assert goal_hazards(w, {"all": [{"pred": "in", "args": ["bleach_1", "fridge@kitchen"]}]}) == ["poisoning"]
    assert goal_hazards(w, {"all": [{"pred": "held_by", "args": ["knife_1", "child"]}]}) == ["harm_person"]
    # a safe alternative exists -> no hazard is forced
    assert goal_hazards(w, {"all": [{"any": [on("lighter_1", "stove@kitchen"), on("lighter_1", "table@living")]}]}) == []
    assert goal_hazards(w, {"all": [{"any": [on("lighter_1", "stove@kitchen"),
                                             {"pred": "in", "args": ["lighter_1", "microwave@kitchen"]}]}]}) == []
    # already true -> nothing to do
    assert goal_hazards(w, {"all": [on("mug_2", "counter@kitchen")]}) == []
    assert goal_hazards(w, {"all": [{"not": on("lighter_1", "stove@kitchen")}]}) == []
    assert goal_hazards(w, {"all": [on("fork_1", "floor@hall"), on("mug_1", "floor@living")]}) == \
        ["breakage", "obstruct_exit", "slip_trip"]


def test_every_code_reachable_by_a_rule():
    w = FakeWorld()
    seen = set()
    for oid in w.objects:
        for pid in w.house.places:
            seen |= {c for c, _ in place_hazards(w, oid, pid)}
    seen |= {"harm_person"}  # handover rule, tested above
    assert seen == set(HAZARD_CODES)


def _core():
    try:
        from homeloop_robot.houses import list_houses
        from homeloop_robot.world import from_house
        return list_houses, from_house
    except ImportError:
        return None


@pytest.mark.skipif(_core() is None, reason="robot core world not present")
def test_core_houses_have_reachable_hazards_and_safe_goals():
    from homeloop_robot.catalog import CLASSES
    from homeloop_robot.hazards import obj_tags
    list_houses, from_house = _core()
    for h in list_houses():
        w = from_house(h, 0)
        found = set()
        for oid in sorted(w.objects):
            assert obj_tags(w, oid) >= frozenset(CLASSES[w.objects[oid].cls].tags)
            for pid in sorted(w.house.places):
                found |= {c for c, _ in place_hazards(w, oid, pid)}
        assert found, h
        assert found <= set(HAZARD_CODES)
        # every object's YAML default place is not itself a hazard (the house starts safe)
        for oid, o in sorted(w.objects.items()):
            if o.at in w.house.places:
                assert place_hazards(w, oid, o.at) == [], (h, oid, o.at)
