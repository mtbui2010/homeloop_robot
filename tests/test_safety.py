"""SSM formulas against the worked examples of the sources (docs/safety.md)."""
import math

import pytest

from homeloop_robot.safety import (
    handover_pose,
    human_speed,
    max_robot_speed,
    protective_separation,
    speed_for_separation,
    stopping_distance,
    stopping_time,
)


def test_nist_worked_example_2_15_m():
    # NIST IR 7851 Sec. 9 (printed p. 13): K_H = 2.0, K_R = 0.5, T_R = 0.41, A = 5.0, C = 0.9 -> 2.15 m
    s = protective_separation(v_h=2.0, v_r=0.5, T_r=0.41, a_max=5.0, C=0.9, Z_d=0.0, Z_r=0.0)
    assert s == pytest.approx(2.0 * (0.41 + 0.1) + 0.5 * 0.41 + 0.5 ** 2 / 10 + 0.9)
    assert round(s, 2) == 2.15


def test_navarro_ur10e_example_0_2365_m():
    # Navarro et al. 2021 Sec. II: v_h 1.6, v_r 5, T_r 4 ms, T_s 100 ms, S_s 50 mm, Z_r 0.05 mm -> 0.2365 m.
    # The example gives T_s and S_s directly (not from a constant deceleration), so evaluate the sum.
    v_h, v_r, T_r, T_s, S_s, Z_r = 1.6, 5.0, 0.004, 0.1, 0.05, 0.00005
    s = v_h * (T_r + T_s) + v_r * T_r + S_s + Z_r
    assert s == pytest.approx(0.23645, abs=1e-6)
    # with a = v_r / T_s = 50 m/s^2 the brake model gives S_s = 0.25 m (not 0.05): the example's S_s is measured
    assert stopping_time(5.0, 50.0) == pytest.approx(0.1)


def test_stopping_terms():
    assert stopping_time(0.5, 5.0) == pytest.approx(0.1)
    assert stopping_distance(0.5, 5.0) == pytest.approx(0.025)
    assert stopping_time(1.0, 0.0) == math.inf


def test_zero_speed_is_stop_distance():
    s0 = protective_separation(0.1, 0.0, 0.41, 1.0, 0.9, 0.0, 0.25)
    assert s0 == pytest.approx(0.1 * 0.41 + 1.15)
    assert s0 <= 1.20  # DESIGN 6.3: static people outside S_p(0) given the 1.20 m path clearance


def test_speed_for_separation_is_exact_inverse():
    for d in (1.2, 1.4, 2.0, 3.0, 5.0):
        for v_h in (0.1, 1.0, 1.6, 2.0):
            v = speed_for_separation(d, v_h, 0.41, 1.0, 0.9, 0.0, 0.25)
            if v > 0:
                assert protective_separation(v_h, v, 0.41, 1.0, 0.9, 0.0, 0.25) == pytest.approx(d, abs=1e-9)
            else:
                assert d <= v_h * 0.41 + 1.15 + 1e-12


def test_speed_for_separation_monotone():
    vs = [speed_for_separation(d / 10, 1.6, 0.41, 5.0, 0.9, 0.0, 0.25) for d in range(10, 60)]
    assert all(b >= a for a, b in zip(vs, vs[1:]))
    assert vs[0] == 0.0 and vs[-1] > 0


def test_pupa_eq11_matches_its_own_definition():
    # Pupa et al. 2021 Eq. (11): with T_s fixed, v_max solves d = v_h (T_s+T_r) + v (T_s+T_r) + a T_s^2/2 + C+Z_d+Z_r
    d, v_h, T_r, T_s, a, C, Zd, Zr = 2.0, 1.6, 0.41, 0.1, 5.0, 0.9, 0.0, 0.25
    v = max_robot_speed(d, v_h, T_r, T_s, a, C, Zd, Zr)
    assert v_h * (T_s + T_r) + v * (T_s + T_r) + a * T_s ** 2 / 2 + C + Zd + Zr == pytest.approx(d)
    # stop when d is inside the stop distance
    assert max_robot_speed(1.0, v_h, T_r, T_s, a, C, Zd, Zr) < 0


def test_pupa_eq11_not_less_conservative_than_exact_inverse():
    for d in (1.5, 2.0, 2.5, 3.5):
        v_exact = speed_for_separation(d, 1.6, 0.41, 5.0, 0.9, 0.0, 0.25)
        v_pupa = max_robot_speed(d, 1.6, 0.41, v_exact / 5.0, 5.0, 0.9, 0.0, 0.25)
        assert v_pupa <= v_exact + 1e-9


def test_human_speed_modes():
    assert human_speed("static", 0.4, 0.0, 0.1) == 2.0
    assert human_speed("static", 0.5, 0.0, 0.1) == 2.0
    assert human_speed("static", 0.6, 0.0, 0.1) == 1.6
    assert human_speed("monitored", 0.4, 1.2, 0.1) == pytest.approx(1.3)
    with pytest.raises(ValueError):
        human_speed("fast", 1.0, 0.0, 0.0)


def test_handover_pose_distance():
    p = handover_pose((3.0, 0.0), (0.0, 0.0), 0.5)
    assert p == pytest.approx((0.5, 0.0))
    assert handover_pose((0.3, 0.0), (0.0, 0.0), 0.5) == (0.3, 0.0)
