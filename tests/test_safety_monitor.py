"""SafetyMonitor.traverse: zones, stops, aborts, violations, handover, determinism, ideal constraint."""
import itertools
import math

import pytest

from _hs_helpers import FakeWorld, Streams, core_profile, load_params, static_people, walker, world_available
from homeloop_robot.safety import SafetyMonitor, protective_separation


def mon(name="real", world=None, seed=0, **ov):
    w = world or FakeWorld()
    return SafetyMonitor(w, load_params(name, **ov), Streams(seed)), w


def nobody(t):
    return {}


def test_free_motion_takes_nominal_time():
    m, w = mon("ideal")
    tr = m.traverse("move", [(3.5, 1.5), (4.5, 1.5)], 0.3, 0.0, nobody)
    assert tr.duration_s == pytest.approx(1.0 / 0.3, abs=1e-6)
    assert tr.slow_s == 0 and tr.stopped_s == 0 and not tr.aborted
    assert tr.min_sep_m is None and tr.violations == ()


def test_zero_length_path():
    m, _ = mon("ideal")
    tr = m.traverse("move", [(1.0, 1.0)], 0.3, 5.0, nobody)
    assert tr.duration_s == 0.0


def test_far_person_no_slowdown():
    m, w = mon("ideal")
    ppl = lambda t: static_people(w)  # noqa: E731  grandma at (1.0, 4.2)
    tr = m.traverse("move", [(4.5, 0.8), (4.5, 1.8)], 0.3, 0.0, ppl)
    assert tr.slow_s == 0 and tr.stopped_s == 0
    assert tr.min_sep_m == pytest.approx(math.dist((4.5, 1.8), (1.0, 4.2)), abs=1e-6)


def test_slow_zone_stretches_duration():
    m, w = mon("ideal")
    # pass 1.25 m from a static person: inside S_p(v_nominal) = 1.39 m but outside S_p(0) = 1.191 m
    person = (2.0, 2.0)
    w.people["grandma"].pos = person
    ppl = lambda t: static_people(w)  # noqa: E731
    tr = m.traverse("move", [(0.5, 0.75), (3.5, 0.75)], 0.3, 0.0, ppl)
    assert tr.slow_s > 0 and tr.stopped_s == 0 and not tr.aborted
    assert tr.duration_s > 3.0 / 0.3
    assert tr.min_sep_m == pytest.approx(1.25, abs=0.02)
    assert tr.violations == ()


def test_static_person_in_path_aborts_after_timeout():
    m, w = mon("ideal")
    w.people["grandma"].pos = (2.0, 1.0)
    ppl = lambda t: static_people(w)  # noqa: E731
    tr = m.traverse("move", [(0.5, 1.0), (3.5, 1.0)], 0.3, 0.0, ppl)
    p = load_params("ideal")
    assert tr.aborted
    assert tr.stopped_s == pytest.approx(p["safety.stop_timeout_s"] + 0.1, abs=0.11)
    assert tr.violations == ()
    s = m.stats()
    assert s["n_protective_stops"] == 1 and s["n_stop_aborts"] == 1


def test_person_crossing_causes_stop_then_resume():
    m, w = mon("ideal")
    # person walks across the robot's path and leaves; robot waits and then finishes
    ppl = walker("grandma", (2.0, 4.5), (2.0, -3.0), 1.0, t_start=0.0)
    tr = m.traverse("move", [(0.2, 1.0), (4.0, 1.0)], 0.3, 0.0, ppl)
    assert not tr.aborted
    assert tr.stopped_s > 0 or tr.slow_s > 0
    assert tr.violations == ()  # ideal: perfect perception -> no violation


def test_detection_miss_can_cause_violation_and_is_seeded():
    # person walks toward the robot while the detector misses every window -> stale position -> violation
    def run(seed):
        m, w = mon("real", seed=seed, **{"safety.p_detection_miss": 1.0})
        ppl = walker("grandma", (5.5, 1.0), (0.5, 1.0), 1.0, t_start=0.0)
        m._last_seen["grandma"] = (0.0, (5.5, 1.0), (0.0, 0.0))
        return m.traverse("move", [(0.5, 1.0), (1.5, 1.0)], 0.3, 0.0, ppl), m

    tr, m = run(1)
    assert tr.violations, "a blind monitor must let the robot violate the separation"
    v = tr.violations[0]
    assert v.cause == "detection_miss" and v.d < v.s_p and v.v_r > 0
    assert any(x.severe for x in tr.violations)
    assert m.stats()["violations"] == len(tr.violations)
    tr2, _ = run(1)
    assert tr2 == tr


def test_real_profile_deterministic():
    def run():
        m, w = mon("real", seed=7)
        ppl = walker("grandma", (5.5, 1.2), (0.5, 1.2), 1.1, t_start=0.0)
        return m.traverse("move", [(0.5, 1.0), (5.0, 1.0)], 0.3, 0.0, ppl)
    assert run() == run()


def test_people_in_other_rooms_ignored():
    m, w = mon("ideal")
    w.people["grandma"].pos = (6.5, 1.0)  # kitchen, 0.5 m from the wall-side path end
    ppl = lambda t: static_people(w)  # noqa: E731
    tr = m.traverse("move", [(3.0, 1.0), (5.9, 1.0)], 0.3, 0.0, ppl)
    assert tr.stopped_s == 0 and tr.min_sep_m is None


def test_arm_traverse_needs_duration_and_stretches():
    m, w = mon("ideal")
    assert m.traverse("pick", [(3.5, 1.5)], 0.4, 0.0, nobody, part="arm").duration_s == 0.0  # no nominal_s
    tr = m.traverse("pick", [(3.5, 1.5)], 0.4, 0.0, nobody, part="arm", nominal_s=8.0)
    assert tr.duration_s == pytest.approx(0.0)  # arm: duration_s is the EXTRA time (types.Traverse)
    w.people["grandma"].pos = (3.5, 2.8)  # 1.3 m away: slow zone for the arm (S_p(0.4) = 1.38 m)
    ppl = lambda t: static_people(w)  # noqa: E731
    tr2 = m.traverse("pick", [(3.5, 1.5)], 0.4, 0.0, ppl, part="arm", nominal_s=8.0)
    assert tr2.duration_s > 0.0 and tr2.slow_s > 0 and tr2.stopped_s == 0


def test_bad_part():
    m, _ = mon("ideal")
    with pytest.raises(ValueError):
        m.traverse("move", [(0, 0), (1, 0)], 0.3, 0.0, nobody, part="leg")


def test_dock_is_muted_and_capped():
    m, w = mon("ideal")
    p = load_params("ideal")
    tr = m.traverse("dock", [(4.5, 1.8), (4.5, 0.8)], 1.0, 0.0, nobody, part="dock")
    assert tr.duration_s == pytest.approx(1.0 / p["safety.muted_speed_mps"], abs=1e-6)


def test_handover_excludes_receiver_and_caps_speed():
    m, w = mon("ideal")
    p = load_params("ideal")
    st = static_people(w)
    ppl = lambda t: st  # noqa: E731
    robot = (1.0 + 1.2, 4.2)  # 1.2 m from grandma
    tb, ta = m.handover("grandma", robot, 0.0, ppl, arm_s=2.0)
    assert not tb.aborted and tb.violations == () and ta.violations == ()
    assert tb.duration_s == pytest.approx(0.7 / p["safety.handover_speed_mps"], abs=1e-6)
    # the arm moves 2 s x arm speed at the handover cap; the extra time over the nominal 2 s is returned
    assert ta.duration_s == pytest.approx(2.0 * p["safety.arm_speed_mps"] / p["safety.handover_speed_mps"] - 2.0,
                                          abs=1e-6)
    assert tb.min_sep_m is None  # the receiver is not counted


def test_stats_shape():
    m, w = mon("ideal")
    m.traverse("move", [(3.5, 1.5), (4.5, 1.5)], 0.3, 0.0, nobody)
    s = m.stats()
    for k in ("violations", "severe", "min_separation_m", "time_in_slow_s", "n_protective_stops", "semantic",
              "time_in_personal_zone_s"):
        assert k in s


def test_ideal_fake_house_no_protective_stop():
    """DESIGN 6.3: approach poses >= 1.30 m and paths >= 1.20 m from seats -> no stop with static people."""
    m, w = mon("ideal")
    ppl = lambda t: static_people(w)  # noqa: E731
    seats = {p.seat for p in w.people.values()}
    poses = [pl.pos for pid, pl in sorted(w.house.places.items()) if pid not in seats]
    for a, b in itertools.permutations(poses, 2):
        m.traverse("move", w.path(a, b), 0.3, 0.0, ppl)
    s = m.stats()
    assert s["n_protective_stops"] == 0 and s["violations"] == 0


@pytest.mark.skipif(not world_available(), reason="robot core world not present")
def test_ideal_houses_no_protective_stop():
    """DESIGN 6.3 on every core house: static people never stop the robot between approach poses."""
    from homeloop_robot.houses import list_houses
    from homeloop_robot.rng import Streams as S
    from homeloop_robot.user import SimUser
    from homeloop_robot.world import from_house
    prof = core_profile("ideal")
    assert list_houses()
    for h in list_houses():
        w = from_house(h, 0)
        st = S(0, "ideal-check")
        user = SimUser(w, prof, st, "en", None)
        m = SafetyMonitor(w, prof, st)
        seats = {p.seat for p in w.people.values()}
        poses = [tuple(pl.pos) for pid, pl in sorted(w.house.places.items()) if pid not in seats]
        for a, b in itertools.combinations(poses, 2):
            tr = m.traverse("move", w.path(a, b), 0.3, 0.0, user.people_at)
            assert tr.stopped_s == 0 and not tr.aborted, (h, a, b)
        s = m.stats()
        assert s["violations"] == 0 and s["n_protective_stops"] == 0, h


def test_s_p_numbers_used_by_houses():
    p = load_params("ideal")
    s0 = protective_separation(p["safety.v_h_margin"], 0.0, p["safety.T_r"], p["safety.a_max_base"], p["safety.C"],
                               p["safety.Z_d"], p["safety.Z_r"])
    assert s0 <= 1.20


def test_arm_without_nominal_still_stops_and_aborts():
    m, w = mon("ideal")
    w.people["grandma"].pos = (3.5, 2.2)  # 0.7 m from the arm: inside S_p(0)
    ppl = lambda t: static_people(w)  # noqa: E731
    tr = m.traverse("pick", [(3.5, 1.5)], 0.4, 0.0, ppl, part="arm")
    assert tr.aborted and tr.stopped_s > 0
