"""A move to a person stops at one point per person position (skills.person_stop_xy), whatever the robot comes
from, and the robot_agent ENV entry of the person stands there or at the spot beside them (R2-5 B1)."""

import math

import pytest

from homeloop_robot.configs import ra_skills
from homeloop_robot.configs.backend import reset_backend, set_backend
from homeloop_robot.configs.tasks import env_for, person_key, person_target
from homeloop_robot.episode import make_episode
from homeloop_robot.houses import list_houses
from homeloop_robot.skills import person_stop_xy


def _houses():
    return list_houses()


@pytest.mark.parametrize("house", _houses())
def test_move_to_a_person_stops_at_the_same_point_from_anywhere(house):
    ep = make_episode(house, 0, "ideal", 0)
    w = ep.world
    for pid in sorted(w.people):
        want = person_stop_xy(w, w.person_xy(pid), 1.2)
        n = 0
        for start in [None] + sorted(w.house.places)[::3]:
            if start is not None and not ep.robot.call("move", target=start).ok:
                continue
            r = ep.robot.call("move", target=pid)
            if not r.ok:
                continue
            n += 1
            assert math.dist(w.robot.pose[:2], want) <= 0.05 + 1e-9, (house, pid, start)
        assert n >= 1, (house, pid)


@pytest.mark.parametrize("house", _houses())
def test_env_entry_of_a_person(house):
    ep = make_episode(house, 0, "ideal", 0)
    env = env_for(ep.world)
    for pid in sorted(ep.world.people):
        e = env[person_key(pid)]
        assert e["person"] == pid
        assert person_target(env, person_key(pid), ep.world) == (pid, e["spot"])
        if e["spot"] is None:
            sx, sy = person_stop_xy(ep.world, ep.world.person_xy(pid), 1.2)
            assert (e["loc"]["x"], e["loc"]["y"]) == pytest.approx((sx, sy))
        else:
            p = ep.world.house.places[e["spot"]]
            assert (e["loc"]["x"], e["loc"]["y"]) == pytest.approx(tuple(p.pos[:2]))


def test_ra_skills_move_to_a_person_without_robot_agent_env():
    ep = make_episode("korean_apt_59", 0, "ideal", 0)
    set_backend(ep.robot)
    try:
        env = env_for(ep.world)
        r = ra_skills.move(None, inputs="person_user")
        assert r["isdone"], r
        loc = env["person_user"]["loc"]
        assert math.dist(ep.world.robot.pose[:2], (loc["x"], loc["y"])) <= 0.3
    finally:
        reset_backend()
