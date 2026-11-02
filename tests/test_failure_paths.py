"""Every injected failure code / event has a test (review round 1): dropped (place, handover), e-stop by
rate, move timeout, wrong instance, false positive, partial open, handover not taken; help requests only
about the active fault; stale path faults; safety monitor on whole arm motions, docking and handover;
the oracle asks for help only when the user can hear it."""

from helpers import episode, patched
from homeloop_robot import make_episode
from homeloop_robot import oracle
from homeloop_robot.types import FailureCode as F
from homeloop_robot.types import FaultState

ALL1 = {"low": 1.0, "medium": 1.0, "high": 1.0}


def go(ep, skill, **a):
    return ep.robot.call(skill, **a)


def _holding_mug(prof, **kw):
    ep = episode(profile=prof, **kw)
    assert go(ep, "move", target="counter@kitchen").ok
    assert go(ep, "find", obj="mug_1").ok
    assert go(ep, "pick", obj="mug_1").ok
    return ep


def test_place_drop():
    ep = _holding_mug(patched(place__p_drop=1.0))
    r = go(ep, "place", target="counter@kitchen")
    assert r.code == F.DROPPED and r.injected and ep.world.robot.holding is None
    assert ep.world.objects["mug_1"].at.startswith("floor@")


def test_handover_drop_and_not_taken():
    def holding_near_grandma(prof):
        ep = make_episode("senior_flat", 0, prof, 0, key="t")
        for c in oracle.solve(ep.world, {"all": [{"pred": "held_by", "args": ["mug_1", "grandma"]}]})[:-1]:
            assert go(ep, c.skill, **c.args).ok, c
        return ep
    ep = holding_near_grandma(patched(handover__p_drop=1.0))
    r = go(ep, "handover", person="grandma")
    assert r.code == F.DROPPED and r.truth["event"] == "drop"
    ep = holding_near_grandma(patched(**{"user__p_unresponsive": 1.0}))
    r = go(ep, "handover", person="grandma")
    assert r.code == F.TIMEOUT and r.truth["event"] == "not_taken" and ep.world.robot.holding == "mug_1"


def test_estop_by_rate():
    ep = episode(profile=patched(estop__rate_per_h=1e9))
    r = go(ep, "move", target="counter@kitchen")
    assert r.code == F.ESTOP and r.injected and ep.world.robot.estop
    assert go(ep, "move", target="counter@kitchen").code == F.ESTOP and go(ep, "say", text="hi").ok


def test_move_timeout():
    ep = episode(profile=patched(move__p_timeout=1.0))
    r = go(ep, "move", target="counter@kitchen")
    assert r.code == F.TIMEOUT and r.truth["event"] == "timeout"


def test_find_wrong_instance_and_false_positive():
    ep = episode(profile=patched(find__p_wrong_instance={"few": 1.0, "many": 1.0}))
    ep.world.objects["mug_2"].at = "counter@kitchen"
    go(ep, "move", target="counter@kitchen")
    r = go(ep, "find", obj="mug_1")
    assert r.ok and r.data["found"] == "mug_2" and r.truth["event"] == "wrong_instance"
    ep = episode(profile=patched(find__p_false_positive=1.0))
    go(ep, "move", target="counter@kitchen")
    r = go(ep, "find", obj="remote_1")                  # on the coffee table, not here
    assert r.ok and r.truth["event"] == "false_positive" and r.truth["effect"] is False


def test_partial_open_via_the_failure_model():
    ep = episode(profile=patched(verify__p_false_success=1.0))
    go(ep, "move", target="fridge@kitchen")
    r = go(ep, "open", container="fridge@kitchen")
    assert r.ok and r.truth["event"] == "partial_open" and "fridge@kitchen" in ep.world.robot.partial_open


def _sim(prof="ideal"):
    return make_episode("senior_flat", 0, prof, 0, key="t")


def test_question_with_a_stale_path_fault_gets_its_real_answer():
    ep = _sim()
    q = "Where is the remote control?"
    ep.world.faults["path:counter@kitchen"] = FaultState(device="path:counter@kitchen", code=F.BLOCKED, since_t=0.0,
                                                         clears_on="retry", p_clear=0.0, p_help=1.0)
    r = go(ep, "ask", question=q)
    assert r.ok and r.truth["reply_kind"] != "yes" and "coffee table" in r.truth["reply"].lower()
    assert "path:counter@kitchen" in ep.world.faults and "help_cleared" not in r.truth
    # right after the blocked move, the ask is about the obstacle: the user clears it
    assert go(ep, "move", target="counter@kitchen").code == F.BLOCKED
    r = go(ep, "ask", question="Can you help me?")
    assert r.truth["reply_kind"] == "yes" and r.truth.get("help_cleared") == ["path:counter@kitchen"]


def test_successful_move_elsewhere_drops_stale_path_faults():
    ep = _sim()
    ep.world.faults["path:counter@kitchen"] = FaultState(device="path:counter@kitchen", code=F.BLOCKED, since_t=0.0,
                                                         clears_on="retry", p_clear=0.0, p_help=1.0)
    assert go(ep, "move", target="coffee_table@living").ok
    assert not any(k.startswith("path:") for k in ep.world.faults)


def test_arm_motion_is_monitored_for_its_whole_duration():
    """A person next to the robot during a pick (real profile) slows or stops the arm for the whole motion,
    not only its first tick."""
    ep = make_episode("senior_flat", 0, "real", 0, key="t")
    ep.world.robot.pose = (0.9, 0.5, 0.0)       # 0.4 m from grandma's chair
    ep.world.robot.at = None
    from homeloop_robot.skills import Robot
    calls = []
    orig = ep.safety.traverse

    def spy(*a, **k):
        calls.append(k)
        return orig(*a, **k)
    ep.safety.traverse = spy
    ep.robot._arm_safety(type("R", (), {"dur": 8.0, "fail": lambda *a, **k: None, "truth": {}})(), "pick")
    assert calls and calls[-1]["part"] == "arm" and calls[-1]["nominal_s"] == 8.0
    st = ep.safety.stats()
    assert st["time_in_slow_s"] + st["time_stopped_s"] > 0.1      # more than one 0.1 s probe tick
    assert Robot


def test_dock_uses_the_muted_monitor():
    ep = _sim("real")
    parts = []
    orig = ep.safety.traverse
    ep.safety.traverse = lambda *a, **k: (parts.append(k.get("part")), orig(*a, **k))[1]
    r = go(ep, "dock")
    assert "dock" in parts and (r.ok or r.code in (F.BLOCKED, F.HW_FAULT))


def test_handover_approaches_the_person():
    ep = _sim()
    for c in oracle.solve(ep.world, {"all": [{"pred": "held_by", "args": ["mug_1", "grandma"]}]})[:-1]:
        assert go(ep, c.skill, **c.args).ok
    seen = []
    orig = ep.safety.handover
    ep.safety.handover = lambda *a, **k: (seen.append(k), orig(*a, **k))[1]
    r = go(ep, "handover", person="grandma")
    assert r.ok and seen and seen[0]["arm_s"] > 0


def test_oracle_waits_instead_of_asking_when_nobody_hears():
    ep = _sim()
    w = ep.world
    xy = tuple(w.robot.pose[:2])
    assert ep.user.hears(ep.user.user_id, xy, 0.0, False)
    assert oracle.recovery_call("blocked", "move", w, ep.user, 0.0).skill == "ask"
    w.robot.pose = (*w.place("bed@bedroom").pos, 0.0)      # grandma stays in the living room
    assert oracle.recovery_call("blocked", "move", w, ep.user, 0.0).skill == "wait"
    assert oracle.recovery_call("perception_unavailable", "find", w, ep.user, 0.0).skill == "wait"
    assert oracle.recovery_call("grasp_failed", "pick", w, ep.user, 0.0) is None
