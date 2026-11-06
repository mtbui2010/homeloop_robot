"""H1 (lab round 3): the ENV loc of a person entry with no spot and the point where the move to that person stops
come from ONE position. The entry is built from the start world; when the person sits down elsewhere afterwards and
no free surface is beside them either, the entry used to keep the old stop point (refresh_person_spot returned early
on new == old) while the move ended at the new seat, so robot_agent's arrival check failed.

Generic fixture: every house, the first person with a seat to walk to, no free surface anywhere."""
import math
import types

import pytest

from homeloop_robot.configs import ra_skills
from homeloop_robot.configs.backend import reset_backend, set_backend
from homeloop_robot.configs.tasks import env_for, person_key, refresh_person_spot
from homeloop_robot.episode import make_episode
from homeloop_robot.houses import list_houses


def _arrive_tol():
    import yaml
    from pathlib import Path
    import homeloop_robot.configs as C
    m = yaml.safe_load((Path(C.__file__).parent / "manifest.yaml").read_text())
    return float(m["geometry"]["arrive_tol_m"])


def _cases():
    out = []
    for h in list_houses():
        w = make_episode(h, 0, "ideal", 0).world
        for pid in sorted(w.people):
            out.append((h, pid))
    return out


def _walk(ep, pid):
    """Schedule one walk of ``pid`` to the seat farthest from them, starting at t=1 s; returns (seat, t_end)."""
    w, u = ep.world, ep.user
    start = tuple(map(float, w.people[pid].pos))
    dests = [d for d in u.destinations(pid) if d != w.people[pid].seat]
    if not dests:
        return None
    dest = max(dests, key=lambda d: math.dist(start, u._seat_pos(pid, d)))
    dpos = u._seat_pos(pid, dest)
    if math.dist(start, dpos) < 1.0:
        return None
    from homeloop_robot.user import polyline_length, world_path
    path = world_path(w, start, dpos)
    dur = polyline_length(path) / u._speed[pid]
    u._sched[pid] = [(1.0, 1.0 + dur, path, dest)]
    return dest, 1.0 + dur


@pytest.fixture
def backend(monkeypatch):
    def use(ep, env):
        set_backend(ep.robot)
        monkeypatch.setattr(ra_skills, "_env", lambda: env)
    yield use
    reset_backend()


@pytest.mark.parametrize("house,pid", _cases())
def test_person_who_walked_elsewhere_is_reached_at_the_env_loc(house, pid, backend, monkeypatch):
    ep = make_episode(house, 0, "ideal", 0)
    w = ep.world
    walk = _walk(ep, pid)
    if walk is None:
        pytest.skip("no other seat to walk to")
    dest, t_end = walk
    # no surface has room for anything, before and after the walk: the entry has no spot at any time
    monkeypatch.setattr(w, "free_slots", lambda plid: 0)
    env = env_for(w)
    key = person_key(w, pid)
    e = env[key]
    assert e["spot"] is None
    before = dict(e["loc"])
    backend(ep, env)
    ep.robot.idle(t_end + 1.0 - ep.robot.clock.t)               # the walk is over
    assert w.person_xy(pid) != tuple(map(float, w.people[pid].pos))
    r = ra_skills.move(None, inputs=key)
    assert r["isdone"], r
    assert e["spot"] is None
    loc = e["loc"]
    d = math.dist(w.robot.pose[:2], (loc["x"], loc["y"]))
    tol = _arrive_tol()
    assert d <= tol, (house, pid, round(d, 3), before, loc)
    # robot_agent's own arrival check on the pose the skill reported
    V = pytest.importorskip("robot_agent.core.planning.verify")
    sv = V.StepVerifier(False, set(), robot=types.SimpleNamespace(geometry=types.SimpleNamespace(arrive_tol_m=tol),
                                                                  text=lambda *a, **k: "", has_text=lambda k: False),
                        locate=lambda k: (e["loc"]["x"], e["loc"]["y"]))
    x, y = w.robot.pose[:2]
    res = sv._at_target({"object": key}, "pose", {"x": x, "y": y}, key)
    assert res.ok, res.detail


@pytest.mark.parametrize("house,pid", _cases())
def test_person_who_did_not_move_keeps_the_same_entry(house, pid):
    """KO and EN alike (the entry holds no text): a refresh for a person who stayed changes nothing."""
    ep = make_episode(house, 0, "ideal", 0)
    w = ep.world
    env = env_for(w)
    e = env[person_key(w, pid)]
    before = (dict(e["loc"]), e["height"], e["spot"])
    spot = refresh_person_spot(env, pid, w)
    assert spot == before[2]
    assert (dict(e["loc"]), e["height"], e["spot"]) == before
