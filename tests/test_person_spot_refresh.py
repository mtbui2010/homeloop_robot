"""Gate pilot round 1 (hl-dev-000008): the robot_agent ENV entry of a person is built from the start world, so a
surface beside the person that was full at the start (the nightstand held the blue book the task moves) left the entry
without a spot for the whole episode: Place on grandma failed "a person, use handover" after the book was gone. A move
to the person now looks at the surroundings again when the entry's spot is not usable (tasks.refresh_person_spot), and
the entry follows IN PLACE, so robot_agent's arrival check (against the ENV loc) still holds."""
import math

import pytest

from homeloop_robot.configs import ra_skills
from homeloop_robot.configs.backend import reset_backend, set_backend
from homeloop_robot.configs.tasks import env_for, person_key, refresh_person_spot
from homeloop_robot.episode import make_episode

FILL = ["candle_1", "houseplant_1", "remote_1"]        # three things onto the side table beside grandma (capacity 3)


def _ep_full_side_table():
    ep = make_episode("senior_flat", 0, "ideal", 0)
    w = ep.world
    for o in FILL:
        w.objects[o].at, w.objects[o].inside = "side_table@living", False
    assert w.free_slots("side_table@living") == 0
    return ep, w


@pytest.fixture
def backend(monkeypatch):
    def use(ep, env):
        set_backend(ep.robot)
        monkeypatch.setattr(ra_skills, "_env", lambda: env)
    yield use
    reset_backend()


def test_entry_without_a_spot_gets_the_surface_freed_later(backend):
    ep, w = _ep_full_side_table()
    env = env_for(w)
    key = person_key(w, "grandma")
    e = env[key]
    view = {k: v for k, v in env.items()}          # robot_agent keeps such a copy (AssistLoop Places)
    assert e["spot"] is None                       # nothing free beside her at the start
    stop = dict(e["loc"])
    backend(ep, env)
    # the robot fetches the water bottle; meanwhile the remote leaves the side table
    assert ra_skills.move(None, inputs="counter@kitchen")["isdone"]
    assert ra_skills.find(None, inputs="water bottle")["isdone"]
    assert ra_skills.pick(None, inputs="water bottle")["isdone"]
    w.objects["remote_1"].at = "coffee_table@living"
    r = ra_skills.move(None, inputs=key)
    assert r["isdone"], r
    assert e["spot"] == "side_table@living" and view[key] is e   # the shared entry follows
    loc = view[key]["loc"]
    assert (loc["x"], loc["y"]) != (stop["x"], stop["y"])
    assert math.dist(w.robot.pose[:2], (loc["x"], loc["y"])) <= 0.3   # robot_agent's arrival check holds
    p = ra_skills.place(None, inputs=key)
    assert p["isdone"], p
    assert w.objects["water_bottle_1"].at == "side_table@living"


def test_entry_stays_when_the_surface_is_still_full(backend):
    ep, w = _ep_full_side_table()
    env = env_for(w)
    key = person_key(w, "grandma")
    before = {k: (dict(v["loc"]), v.get("spot")) for k, v in env.items() if isinstance(v, dict) and v.get("person")}
    backend(ep, env)
    assert ra_skills.move(None, inputs="counter@kitchen")["isdone"]
    assert ra_skills.find(None, inputs="water bottle")["isdone"]
    assert ra_skills.pick(None, inputs="water bottle")["isdone"]
    assert ra_skills.move(None, inputs=key)["isdone"]
    after = {k: (dict(v["loc"]), v.get("spot")) for k, v in env.items() if isinstance(v, dict) and v.get("person")}
    assert after == before
    p = ra_skills.place(None, inputs=key)              # still no surface: a Place on her fails as before
    assert not p["isdone"] and "handover" in p["msg"]


def test_a_usable_spot_is_kept():
    ep = make_episode("senior_flat", 0, "ideal", 0)
    w = ep.world
    env = env_for(w)
    e = env[person_key(w, "grandma")]
    assert e["spot"] == "side_table@living"
    loc = dict(e["loc"])
    assert refresh_person_spot(env, "grandma", w) == "side_table@living" and e["loc"] == loc
