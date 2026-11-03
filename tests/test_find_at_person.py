"""Pilot round 2 (hl-dev-000010): Find right after a move to a person (the robot is at no place) reports the object
as not seen (absent), as a robot that looks around there would, not "unreachable" ("out of reach from grandpa")."""
from homeloop_robot.episode import make_episode
from homeloop_robot.types import FailureCode as F


def test_find_beside_a_person_is_absent():
    ep = make_episode("korean_apt_59", 0, "ideal", 0)
    w = ep.world
    assert ep.robot.call("move", target="grandpa").ok
    assert w.robot.at is None
    oid = sorted(w.objects)[0]
    r = ep.robot.call("find", obj=oid)
    assert not r.ok and r.code == F.ABSENT and r.truth.get("event") == "not_at_place", (r.code, r.msg, r.truth)
    assert "reach" not in r.msg
    # back at a place, Find works as before
    at = w.objects[oid].at
    if at in w.house.places and ep.robot.call("move", target=at).ok and oid in w.visible_at(at):
        assert ep.robot.call("find", obj=oid).ok
