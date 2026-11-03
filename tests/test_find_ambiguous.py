"""Gate pilot round 1 (hl-dev-000019 / 000017 / 000027): Find with a name several objects fit ("mug" with a red and
a blue mug in the house) looks for that name where the robot is, as a detector does. It used to fail "mug not found:
which one?" wherever the robot looked, even in front of both mugs, so the planner searched elsewhere."""
from homeloop_robot.types import FailureCode as F

from helpers import episode


def _at(ep, place):
    assert ep.robot.call("move", target=place).ok
    assert ep.world.robot.at == place


def test_one_fitting_object_in_view_is_found_and_picked():
    ep = episode("senior_flat")
    w = ep.world
    assert w.resolve_object("mug", None) == ["mug_1", "mug_2"]
    _at(ep, "counter@kitchen")                       # the red mug is here, the blue one on the kitchen shelf
    r = ep.robot.call("find", obj="mug")
    assert r.ok and r.data["found"] == "mug_1", (r.code, r.msg)
    assert "candidates" not in r.data
    p = ep.robot.call("pick", obj="mug")             # the planner picks by the same name
    assert p.ok and w.robot.holding == "mug_1", (p.code, p.msg)


def test_several_fitting_objects_in_view_one_is_found_and_the_result_lists_them():
    ep = episode("senior_flat")
    w = ep.world
    _at(ep, "nightstand@bedroom")                    # two medicine bottles stand here
    r = ep.robot.call("find", obj="medicine bottle")
    assert r.ok and r.data["found"] in ("medicine_bottle_1", "medicine_bottle_2"), (r.code, r.msg)
    assert sorted(r.data["candidates"]) == ["medicine_bottle_1", "medicine_bottle_2"]
    assert ep.robot.call("pick", obj="medicine bottle").ok
    assert w.robot.holding == r.data["found"]


def test_no_fitting_object_in_view_is_plain_not_found():
    ep = episode("senior_flat")
    _at(ep, "counter@kitchen")                       # the books are on the coffee table and the nightstand
    r = ep.robot.call("find", obj="book")
    assert not r.ok and r.code == F.ABSENT and r.truth.get("event") == "not_here", (r.code, r.msg)
    assert "which one" not in r.msg and "candidates" not in r.data
    # an unknown name is still "no such object"; a specific name works as before
    assert "no such object" in ep.robot.call("find", obj="umbrella stand").msg
    _at(ep, "coffee_table@living")
    assert ep.robot.call("find", obj="red book").ok


def test_pick_of_an_ambiguous_name_without_a_find_stays_unresolved():
    ep = episode("senior_flat")
    _at(ep, "counter@kitchen")
    p = ep.robot.call("pick", obj="mug")
    assert not p.ok and p.code == F.ABSENT and sorted(p.data["candidates"]) == ["mug_1", "mug_2"]
