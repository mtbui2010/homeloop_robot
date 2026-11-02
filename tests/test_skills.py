import pytest

from helpers import HAS_RA, episode, patched
from homeloop_robot.skills import SKILL_SPECS
from homeloop_robot.types import FailureCode as F, UserEvent


def go(ep, skill, **a):
    return ep.robot.call(skill, **a)


def test_specs_cover_all_skills():
    assert set(SKILL_SPECS) == {"move", "find", "pick", "place", "put_in", "open", "close", "handover", "say",
                                "announce", "ask", "look", "vlm_check", "wait", "dock", "grasp_check", "pose"}


def test_bad_args_are_software_errors_without_time():
    ep = episode()
    r = go(ep, "move")
    assert r.code == F.SOFTWARE and r.duration_s == 0
    assert go(ep, "move", target="x", speed=3).code == F.SOFTWARE
    assert go(ep, "fly").code == F.SOFTWARE
    assert go(ep, "wait", seconds=500).code == F.SOFTWARE
    assert ep.clock.t == 0


def test_pick_place_flow_ideal():
    ep = episode()
    w = ep.world
    assert go(ep, "pick", obj="mug_1").code == F.ABSENT              # not found yet
    assert go(ep, "move", target="kitchen counter").ok
    assert w.robot.at == "counter@kitchen"
    assert go(ep, "move", target="counter@kitchen").duration_s == 0  # already there
    r = go(ep, "find", obj="red mug")
    assert r.ok and r.data["found"] == "mug_1"
    assert go(ep, "pick", obj="mug_1").ok and w.robot.holding == "mug_1"
    assert go(ep, "pick", obj="glass_1").code == F.GRASP_FAILED      # hand full
    assert go(ep, "move", target="coffee_table@living").ok
    assert go(ep, "place", target="coffee_table@living").ok
    assert w.objects["mug_1"].at == "coffee_table@living" and w.robot.holding is None
    assert go(ep, "place", target="coffee_table@living").code == F.ABSENT          # nothing held
    assert ep.clock.t > 0 and all(t["injected"] is False for t in ep.robot.trace)


def test_containers():
    ep = episode()
    w = ep.world
    go(ep, "move", target="fridge@kitchen")
    assert go(ep, "find", obj="milk_1").code == F.ABSENT                 # inside a closed fridge
    assert go(ep, "open", container="fridge@kitchen").ok and "fridge@kitchen" in w.opened
    assert go(ep, "find", obj="milk_1").ok
    assert go(ep, "pick", obj="milk_1").ok
    assert go(ep, "close", container="fridge@kitchen").code == F.BLOCKED  # hand full
    assert go(ep, "put_in", container="fridge@kitchen").ok and w.objects["milk_1"].inside
    assert go(ep, "close", container="fridge@kitchen").ok and "fridge@kitchen" not in w.opened
    go(ep, "move", target="counter@kitchen")
    assert go(ep, "open", container="counter@kitchen").code == F.BLOCKED  # not a container
    assert go(ep, "open", container="fridge@kitchen").code == F.UNREACHABLE  # not there


def test_put_in_closed_and_not_container():
    ep = episode()
    go(ep, "move", target="counter@kitchen")
    go(ep, "find", obj="mug_1")
    go(ep, "pick", obj="mug_1")
    go(ep, "move", target="drawer@kitchen")
    assert go(ep, "put_in", container="drawer@kitchen").code == F.BLOCKED
    go(ep, "move", target="counter@kitchen")
    assert go(ep, "put_in", container="counter@kitchen").code == F.UNREACHABLE


def test_heavy_and_ambiguous():
    ep = episode()
    go(ep, "move", target="tv_stand@living")
    go(ep, "find", obj="houseplant_1")
    r = go(ep, "pick", obj="houseplant_1")
    assert r.code == F.GRASP_FAILED and "too heavy" in r.msg
    assert go(ep, "find", obj="mug").code == F.ABSENT                    # two mugs: which one
    assert go(ep, "move", target="nowhere").code == F.UNREACHABLE


def test_handover_say_ask_dock():
    ep = episode()
    w = ep.world
    go(ep, "move", target="nightstand@bedroom")
    go(ep, "find", obj="glasses_1")
    go(ep, "pick", obj="glasses_1")
    assert go(ep, "handover", person="grandma").code == F.UNREACHABLE     # too far
    assert go(ep, "move", target="grandma").ok
    r = go(ep, "handover", person="")
    assert r.ok and w.objects["glasses_1"].at == "person:grandma"
    r = go(ep, "say", text="Dinner is ready.")
    assert r.ok and r.data["heard_by"] == ["grandma"] and w.utterances[-1].heard_by == ("grandma",)
    assert go(ep, "ask", question="Is it OK?").code == F.TIMEOUT         # the Null user never answers
    assert go(ep, "say", text="").code == F.SOFTWARE
    assert go(ep, "dock").code == F.UNREACHABLE
    go(ep, "move", target="dock")
    assert go(ep, "dock").ok and w.robot.docked


def test_look_vlm_pose_grasp_check_wait():
    ep = episode()
    go(ep, "move", target="counter@kitchen")
    r = go(ep, "look")
    ids = [v["id"] for v in r.data["visible"]]
    assert "mug_1" in ids and "glass_1" in ids and r.data["containers"]["fridge@kitchen"] == "closed"
    assert go(ep, "vlm_check", query="on(mug_1, counter@kitchen)").data["answer"] == "yes"
    assert go(ep, "vlm_check", query="on(red mug, kitchen counter)").data["answer"] == "yes"
    assert go(ep, "vlm_check", query="open(fridge@kitchen)").data["answer"] == "no"
    assert go(ep, "vlm_check", query="gibberish((").data["answer"] == "unknown"
    assert go(ep, "pose").data["at"] == "counter@kitchen"
    assert go(ep, "grasp_check").data["holding"] is False
    t = ep.clock.t
    assert go(ep, "wait", seconds="10").ok and ep.clock.t == pytest.approx(t + 10)


def test_estop_and_persistent_hw_fault():
    ep = episode()
    ep.world.robot.estop = True
    assert go(ep, "move", target="counter@kitchen").code == F.ESTOP
    assert go(ep, "say", text="hello").ok                               # not a motion skill
    ep = episode(profile=patched(hw__p_per_motion_call=1.0, hw__p_persistent=1.0))
    r = go(ep, "move", target="counter@kitchen")
    assert r.code == F.HW_FAULT and r.injected
    r2 = go(ep, "move", target="counter@kitchen")
    assert r2.code == F.HW_FAULT and not r2.injected                    # stays faulted
    assert go(ep, "say", text="hello").ok


def test_scripted_interrupt_cancels_motion_call():
    ep = episode()
    ep.robot.schedule_interrupt(1, UserEvent(t=0, kind="stop", text="Stop!"))
    assert go(ep, "move", target="counter@kitchen").ok
    assert go(ep, "find", obj="mug_1").ok                              # not a motion call
    r = go(ep, "pick", obj="mug_1")
    assert r.code == F.CANCELLED and ep.world.robot.holding is None
    ev = ep.robot.pop_events()
    assert len(ev) == 1 and ev[0].kind == "stop" and ep.robot.pop_events() == []
    assert go(ep, "pick", obj="mug_1").ok


def test_blocked_path_is_sticky_and_help_clears():
    prof = patched(move__p_fail={"low": 1.0, "medium": 1.0, "high": 1.0},
                   move__split={"blocked": 1.0, "unreachable": 0.0},
                   move__p_retry_clears_blocked=0.0, move__p_help_clears_blocked=1.0)
    ep = episode(profile=prof)
    assert go(ep, "move", target="counter@kitchen").code == F.BLOCKED
    assert go(ep, "move", target="counter@kitchen").code == F.BLOCKED   # retry does not clear (p 0)
    assert any(k.startswith("path:") for k in ep.world.faults)
    # the Null user never answers, so a help request does nothing
    go(ep, "ask", question="Could you clear the way?")
    assert any(k.startswith("path:") for k in ep.world.faults)


def test_silent_failures_and_drops():
    ep = episode(profile=patched(verify__p_false_success=1.0))
    w = ep.world
    go(ep, "move", target="counter@kitchen")
    go(ep, "find", obj="mug_1")
    r = go(ep, "pick", obj="mug_1")
    assert r.ok and r.injected is False and r.truth["event"] == "slip" and w.robot.holding is None
    ep = episode(profile=patched(carry__p_drop=1.0))
    go(ep, "move", target="counter@kitchen")
    go(ep, "find", obj="mug_1")
    go(ep, "pick", obj="mug_1")
    r = go(ep, "move", target="coffee_table@living")
    assert r.ok and w is not ep.world and ep.world.objects["mug_1"].at == "floor@living"
    go(ep, "move", target="floor@living")
    assert go(ep, "find", obj="mug_1").ok and go(ep, "pick", obj="mug_1").ok   # a drop is recoverable


def test_camera_down_clears_on_wait():
    ep = episode(profile=patched(perception__p_unavailable=1.0, perception__p_clear_on_wait=1.0))
    go(ep, "move", target="counter@kitchen")
    assert go(ep, "find", obj="mug_1").code == F.PERCEPTION_UNAVAILABLE
    assert "camera" in ep.world.faults
    go(ep, "wait", seconds=5)
    assert "camera" not in ep.world.faults


def test_false_arrival_detected_by_pose():
    ep = episode(profile=patched(move__p_false_arrival_normal=1.0))
    r = go(ep, "move", target="counter@kitchen")
    assert r.ok and r.truth["event"] == "false_arrival" and ep.world.robot.at is None
    assert ep.robot.observe()["at"] == "counter@kitchen"               # the robot believes it arrived
    assert "at" not in go(ep, "pose").data
    assert go(ep, "find", obj="mug_1").code == F.ABSENT


@pytest.mark.skipif(not HAS_RA, reason="robot_agent not importable")
def test_messages_classify_to_their_codes():
    from robot_agent.contract import classify_legacy_failure
    from homeloop_robot.houses import list_houses
    from homeloop_robot.rng import rng_for
    from homeloop_robot.selftest import random_call
    seen = 0
    for prof in ("real", "stress"):
        for h in list_houses():
            ep = episode(h, prof, seed=3, seed_state=3)
            rng = rng_for("cls", h)
            for _ in range(80):
                s, a = random_call(ep.world, rng)
                r = ep.robot.call(s, **a)
                if not r.ok:
                    seen += 1
                    assert classify_legacy_failure(r.msg).value == r.code.value, r.msg
    assert seen > 100
    for msg, code in [("e-stop pressed: the robot cannot move until it is reset", "estop"),
                      ("cancelled by the user", "cancelled"),
                      ("TypeError: move() got an unexpected keyword argument 'x'", "software"),
                      ("could not grasp mug_1: too heavy", "grasp_failed"),
                      ("protective stop: person in the way (blocked)", "blocked"),
                      ("handover timed out: grandma did not take mug_1", "timeout"),
                      ("cannot reach mug_1: fridge@kitchen is only partly open", "unreachable"),
                      ("fridge@kitchen is closed: blocked", "blocked"), ("no free spot on x", "blocked"),
                      ("nothing to place: no object held (not found in the hand)", "absent"),
                      ("cannot reach the handle of fridge@kitchen", "unreachable")]:
        assert classify_legacy_failure(msg).value == code, msg
