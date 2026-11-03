"""The ENV's people (robot_agent's optional ENV contract, docs/robot_agent.md "people tracking"):

* ``people_tracking`` on: each person's entry is where the ROBOT last saw them (world.people_seen, updated only
  while they are in the robot's room), with the speaker flagged, their seat and the spot beside them;
* off: no position, seat or spot: the planner has to ask where the person is;
* places carry ``surface`` (things can be put down on them): never a seat, a bed or the floor.
"""
from homeloop_robot.configs.tasks import env_for, refresh_person_spot
from homeloop_robot.world import from_house


def _world():
    return from_house("senior_flat", 0)


def test_tracking_entries_have_last_seen_position_and_speaker():
    w = _world()
    env = env_for(w)
    ps = [v for v in env.values() if v.get("person")]
    assert ps and all("loc" in v and "spot" in v for v in ps)
    assert sum(1 for v in ps if v["speaker"]) == 1
    places = {k: v for k, v in env.items() if not v.get("person")}
    assert any(v["surface"] for v in places.values()) and not all(v["surface"] for v in places.values())
    for k, v in places.items():
        if w.house.places[k].kind in ("seat", "floor"):
            assert v["surface"] is False


def test_untracked_entries_have_no_position():
    env = env_for(_world(), people_tracking=False)
    ps = [v for v in env.values() if v.get("person")]
    assert ps and all(not ({"loc", "spot", "seat", "height"} & set(v)) for v in ps)
    assert sum(1 for v in ps if v["speaker"]) == 1
    # a refresh of an untracked entry adds no position
    pid = ps[0]["person"]
    assert refresh_person_spot(env, pid, _world()) is None and "loc" not in ps[0]


def test_last_seen_is_stale_out_of_view():
    w = _world()
    pid = sorted(w.people)[0]
    start = w.seen_xy(pid)
    w.people_now[pid] = {"pos": (start[0] + 50.0, start[1]), "moving": False}   # moved, never seen since
    assert w.seen_xy(pid) == start
    w.people_seen[pid] = (1.0, 2.0)
    assert w.seen_xy(pid) == (1.0, 2.0)
