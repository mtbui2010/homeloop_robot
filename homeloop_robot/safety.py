"""Human-aware safety: speed and separation monitoring (SSM) for the mock robot.

Formulas (docs/safety.md has the derivations and sources):

* protective separation, constant-speed form (Navarro et al. 2021, Eq. 1) with the NIST IR 7851 brake model
  ``S_p = v_h (T_r + T_s) + v_r T_r + S_s + C + Z_d + Z_r``, ``T_s = v_r / a_max``, ``S_s = v_r^2 / (2 a_max)``;
* maximum robot speed toward a person (Pupa et al. 2021, Eq. 11);
* human approach speed: 1.6 m/s, 2.0 m/s close in (ISO 13855 as quoted by Campomaggiore et al. 2019), or the
  tracked speed plus a margin in monitored mode.

``SafetyMonitor.traverse`` runs a skill's motion in 0.1 s ticks against the people's true trajectories,
applying free / slow / stop zones (Pupa et al. 2021 Fig. 1, NIST IR 7851 stop + slow), protective stops with
automatic restart, and counts separation violations (d < S_p while moving) and severe ones
(d < C_H + C_R = 1.15 m while moving, NIST IR 7851 Sec. 9).
"""
from __future__ import annotations

import math
from typing import Any, Callable

from homeloop_robot._hs_compat import (
    Traverse,
    Violation,
    dist,
    param,
    point_along,
    polyline_length,
    r6,
    rooms_at,
)

TICK_S = 0.1  # DESIGN 6.2
ARM_PROBE_S = TICK_S  # arm traverse without nominal_s: monitor one tick of arm motion
FAST_WINDOW_S = 1.0  # fast path: one jump of up to 1 s while everybody is far
EPS = 1e-9

# Parameters this module reads (the user-safety block of PARAM_REGISTRY).
PARAMS = (
    "safety.mode",
    "safety.v_h_far",
    "safety.v_h_near",
    "safety.v_h_switch_m",
    "safety.v_h_margin",
    "safety.T_r",
    "safety.a_max_arm",
    "safety.a_max_base",
    "safety.C",
    "safety.Z_d",
    "safety.Z_r",
    "safety.severe_m",
    "safety.arm_speed_mps",
    "safety.handover_distance_m",
    "safety.handover_speed_mps",
    "safety.muted_speed_mps",
    "safety.stop_timeout_s",
    "safety.p_detection_miss",
    "safety.t_r_jitter_s",
    "safety.p_latency_jitter",
    "safety.personal_zone_m",
)


# ------------------------------------------------------------------------------------ pure formulas
def stopping_time(v_r: float, a_max: float) -> float:
    """T_s = v_r / a_max (constant deceleration, NIST IR 7851 brake model)."""
    return v_r / a_max if a_max > 0 else math.inf


def stopping_distance(v_r: float, a_max: float) -> float:
    """S_s = v_r^2 / (2 a_max)."""
    return v_r * v_r / (2.0 * a_max) if a_max > 0 else math.inf


def protective_separation(v_h: float, v_r: float, T_r: float, a_max: float, C: float, Z_d: float,
                          Z_r: float) -> float:
    """Protective separation distance S_p (m).

    S_p = v_h (T_r + T_s) + v_r T_r + S_s + C + Z_d + Z_r with T_s = v_r / a_max and S_s = v_r^2 / (2 a_max)
    (Navarro et al. 2021, Eq. 1; brake terms after NIST IR 7851 Sec. 5).
    """
    T_s = stopping_time(v_r, a_max)
    S_s = stopping_distance(v_r, a_max)
    return v_h * (T_r + T_s) + v_r * T_r + S_s + C + Z_d + Z_r


def max_robot_speed(d: float, v_h: float, T_r: float, T_s: float, a_max: float, C: float, Z_d: float,
                    Z_r: float) -> float:
    """Maximum robot speed toward the person at separation ``d`` (Pupa et al. 2021, Eq. 11).

    v_max = [d - v_h (T_s + T_r) - C - Z_d - Z_r] / (T_s + T_r) - a_max T_s^2 / (2 (T_s + T_r)).
    ``T_s`` is a given stopping time. A value <= 0 means protective stop.
    """
    T = T_s + T_r
    return (d - v_h * T - C - Z_d - Z_r) / T - a_max * T_s * T_s / (2.0 * T)


def speed_for_separation(d: float, v_h: float, T_r: float, a_max: float, C: float, Z_d: float,
                         Z_r: float) -> float:
    """Largest v_r >= 0 with protective_separation(v_h, v_r, ...) <= d (the exact inverse; 0 -> stop).

    With T_s = v_r / a_max the separation is quadratic in v_r:
    v_r^2 / (2a) + v_r (v_h / a + T_r) + (v_h T_r + C + Z_d + Z_r - d) = 0.
    The monitor uses this inverse so that its zones agree with ``protective_separation`` exactly; Pupa's
    Eq. (11) with T_s at the nominal speed is at least as conservative.
    """
    k = v_h * T_r + C + Z_d + Z_r - d
    if k >= 0:
        return 0.0
    b = v_h / a_max + T_r
    disc = b * b - 2.0 * k / a_max
    return max(0.0, a_max * (-b + math.sqrt(disc)))


def human_speed(mode: str, d: float, tracked_speed: float, margin: float, *, v_far: float = 1.6,
                v_near: float = 2.0, switch_m: float = 0.5) -> float:
    """Human speed used in S_p.

    static: the person is not tracked; 2.0 m/s when d <= 0.5 m else 1.6 m/s (ISO 13855 approach speeds as
    quoted by Campomaggiore et al. 2019 and Navarro et al. 2021).
    monitored: the tracked speed plus a margin.
    """
    if mode == "static":
        return v_near if d <= switch_m else v_far
    if mode == "monitored":
        return tracked_speed + margin
    raise ValueError(f"unknown safety mode {mode!r}")


def handover_pose(robot_xy, person_xy, distance_m: float) -> tuple[float, float]:
    """Base pose ``distance_m`` from the person on the line toward the robot (Koay et al. 2014: 0.5 m)."""
    d = dist(robot_xy, person_xy)
    if d <= distance_m or d == 0:
        return (float(robot_xy[0]), float(robot_xy[1]))
    f = distance_m / d
    return (person_xy[0] + f * (robot_xy[0] - person_xy[0]), person_xy[1] + f * (robot_xy[1] - person_xy[1]))


# ------------------------------------------------------------------------------------------ monitor
class SafetyParams:
    """Resolved safety parameters (all from the profile; nothing hard-coded)."""

    def __init__(self, profile: Any):
        g = lambda n: param(profile, n)  # noqa: E731
        self.mode = str(g("safety.mode"))
        self.v_h_far = float(g("safety.v_h_far"))
        self.v_h_near = float(g("safety.v_h_near"))
        self.v_h_switch_m = float(g("safety.v_h_switch_m"))
        self.v_h_margin = float(g("safety.v_h_margin"))
        self.T_r = float(g("safety.T_r"))
        self.a_max_arm = float(g("safety.a_max_arm"))
        self.a_max_base = float(g("safety.a_max_base"))
        self.C = float(g("safety.C"))
        self.Z_d = float(g("safety.Z_d"))
        self.Z_r = float(g("safety.Z_r"))
        self.severe_m = float(g("safety.severe_m"))
        self.arm_speed_mps = float(g("safety.arm_speed_mps"))
        self.handover_distance_m = float(g("safety.handover_distance_m"))
        self.handover_speed_mps = float(g("safety.handover_speed_mps"))
        self.muted_speed_mps = float(g("safety.muted_speed_mps"))
        self.stop_timeout_s = float(g("safety.stop_timeout_s"))
        self.p_detection_miss = float(g("safety.p_detection_miss"))
        self.t_r_jitter_s = float(g("safety.t_r_jitter_s"))
        self.p_latency_jitter = float(g("safety.p_latency_jitter"))
        if self.p_latency_jitter <= 0:
            self.t_r_jitter_s = 0.0
        self.personal_zone_m = float(g("safety.personal_zone_m"))

    def v_h(self, d: float, speed: float) -> float:
        return human_speed(self.mode, d, speed, self.v_h_margin, v_far=self.v_h_far, v_near=self.v_h_near,
                           switch_m=self.v_h_switch_m)

    def v_h_max(self, people_speed_max: float) -> float:
        if self.mode == "static":
            return max(self.v_h_far, self.v_h_near)
        return people_speed_max + self.v_h_margin

    def s_p(self, v_h: float, v_r: float, a_max: float) -> float:
        return protective_separation(v_h, v_r, self.T_r, a_max, self.C, self.Z_d, self.Z_r)

    def s_p0(self, v_h: float) -> float:
        """Stop distance S_p(v_r = 0) = v_h T_r + C + Z_d + Z_r."""
        return v_h * self.T_r + self.C + self.Z_d + self.Z_r


class SafetyMonitor:
    """Speed and separation monitor over the true world (DESIGN 6.2).

    ``traverse`` is called by the robot for every motion skill. The robot base moves along ``path`` at up to
    ``v_nominal`` and ``duration_s`` is the whole motion time; for ``part="arm"`` the base stands at
    ``path[0]``, the arm sweeps ``nominal_s * v_nominal`` metres at up to ``v_nominal``, and ``duration_s`` is
    the EXTRA time (slow-down + stops) the robot adds to the skill's nominal duration; ``part="dock"`` is a base motion with personnel
    detection muted (ISO 3691-4 muting as quoted by a secondary source): the speed is capped at
    ``safety.muted_speed_mps`` and no slow/stop is applied, but separation is still accounted.
    """

    def __init__(self, world: Any, profile: Any, streams: Any):
        self.world = world
        self.profile = profile
        self.streams = streams
        self.p = SafetyParams(profile)
        self._violations: list = []
        self._min_sep: float | None = None
        self._slow_s = 0.0
        self._stopped_s = 0.0
        self._n_stops = 0
        self._n_aborts = 0
        self._comfort_s = 0.0
        self._n_traverse = 0
        self._last_seen: dict[str, tuple[float, tuple[float, float], tuple[float, float]]] = {}

    # ------------------------------------------------------------------ perception model
    def _estimate(self, pid: str, st: Any, t: float, people: Callable):
        """What the monitor believes about person ``pid`` at time t.

        Returns (pos, speed, cause) or None when the person is not detected and was never seen. Two noise
        sources (both zero in ``ideal``): a detection miss per (person, 1 s window) -> the last detected
        position is used (stale); a sensing latency drawn per tick in [0, safety.t_r_jitter_s] -> the position
        that many seconds ago is used.
        """
        p = self.p
        if p.p_detection_miss > 0:
            window = int(math.floor(t + EPS))
            if self.streams.rng_for("safety", "miss", pid, window).random() < p.p_detection_miss:
                if pid not in self._last_seen:
                    return None
                _, lpos, lvel = self._last_seen[pid]
                return lpos, math.hypot(*lvel), "detection_miss"
        pos, vel, cause = tuple(st.pos), tuple(st.vel), None
        if p.t_r_jitter_s > 0:
            rj = self.streams.rng_for("safety", "jitter", pid, round(t, 3))
            lag = rj.uniform(0.0, p.t_r_jitter_s) if (p.p_latency_jitter >= 1 or rj.random() < p.p_latency_jitter) else 0.0
            old = people(max(0.0, t - lag)).get(pid) if lag > 0 else None
            if old is not None and tuple(old.pos) != pos:
                pos, vel, cause = tuple(old.pos), tuple(old.vel), "latency"
        self._last_seen[pid] = (t, pos, vel)
        return pos, math.hypot(*vel), cause

    # ------------------------------------------------------------------ main loop
    def traverse(self, skill: str, path: list, v_nominal: float, t0: float, people: Callable[[float], dict],
                 *, part: str = "base", collaborative_with: str | None = None,
                 nominal_s: float | None = None) -> Traverse:
        p = self.p
        if part not in ("base", "arm", "dock"):
            raise ValueError(f"part must be base, arm or dock, not {part!r}")
        path = [tuple(map(float, q)) for q in path]
        if not path:
            raise ValueError("empty path")
        muted = part == "dock"
        a_max = p.a_max_arm if part == "arm" else p.a_max_base
        v_cap = float(v_nominal)
        if muted:
            v_cap = min(v_cap, p.muted_speed_mps)
        if collaborative_with is not None:
            v_cap = min(v_cap, p.handover_speed_mps)
        if part == "arm":
            if nominal_s is None:
                # degraded mode: only the start of the arm motion is monitored (stop / wait / abort and a
                # violation check); pass nominal_s for the slow-down of the whole motion (DESIGN 6.2)
                nominal_s = ARM_PROBE_S
            length = max(0.0, float(nominal_s)) * float(v_nominal)
        else:
            length = polyline_length(path)
        self._n_traverse += 1
        if length <= EPS or v_cap <= EPS:
            return Traverse(0.0, 0.0, 0.0, False, None, ())

        t, s = float(t0), 0.0
        slow_s = stopped_s = comfort_s = 0.0
        stop_run = 0.0
        aborted = False
        n_stops = 0
        min_sep: float | None = None
        open_viol: dict[str, list] = {}  # person -> [onset t, min d, s_p at min, v_r, v_h, severe, cause]
        closed: list = []

        def close_viol(pid: str) -> None:
            v = open_viol.pop(pid)
            closed.append(Violation(r6(v[0]), skill, pid, r6(v[1]), r6(v[2]), r6(v[3]), r6(v[4]), v[5], v[6]))

        while s < length - EPS:
            xy = path[0] if part == "arm" else point_along(path, s)
            rooms = rooms_at(self.world, xy)
            ppl = people(t)
            considered = []
            for pid in sorted(ppl):
                st = ppl[pid]
                if pid == collaborative_with:
                    continue
                if rooms and st.room is not None and st.room not in rooms:
                    continue  # walls: people in other rooms are neither sensed nor endangered
                considered.append((pid, st))

            # fast path: everybody far beyond S_p for the next window -> one jump at full speed
            dmin = min((dist(xy, st.pos) for _, st in considered), default=math.inf)
            if considered:
                vmax_h = p.v_h_max(max(math.hypot(*st.vel) for _, st in considered))
                far = p.s_p(vmax_h, v_cap, a_max) + 2.0 * (vmax_h + v_cap) * FAST_WINDOW_S
            else:
                far = 0.0
            if dmin > far and (not considered or dmin > p.personal_zone_m):
                dt = FAST_WINDOW_S
                ds = v_cap * dt
                if s + ds > length:
                    dt, ds = (length - s) / v_cap, length - s
                for pid in list(open_viol):
                    close_viol(pid)
                for pid, st in considered:
                    self._last_seen[pid] = (t, tuple(st.pos), tuple(st.vel))
                if considered:
                    min_sep = dmin if min_sep is None else min(min_sep, dmin)
                stop_run = 0.0
                s += ds
                t += dt
                continue

            # zone decision on the monitor's estimates (free / slow / stop)
            v_allowed = v_cap
            causes: dict[str, str | None] = {}
            for pid, st in considered:
                e = self._estimate(pid, st, t, people)
                if e is None:
                    causes[pid] = "detection_miss"
                    continue
                pos_e, spd_e, causes[pid] = e
                if not muted:
                    d_e = dist(xy, pos_e)
                    v_allowed = min(v_allowed, speed_for_separation(d_e, p.v_h(d_e, spd_e), p.T_r, a_max, p.C,
                                                                    p.Z_d, p.Z_r))
            v_r = v_allowed if v_allowed > 1e-6 else 0.0

            # accounting on the TRUE positions
            for pid, st in considered:
                d = dist(xy, st.pos)
                v_h_t = p.v_h(d, math.hypot(*st.vel))
                s_true = p.s_p(v_h_t, v_r, a_max)
                if v_r > 0:
                    min_sep = d if min_sep is None else min(min_sep, d)
                if v_r > 0 and d < s_true - 1e-6:
                    sev = d < p.severe_m
                    if pid not in open_viol:
                        cause = causes.get(pid) or ("muted" if muted else "latency")
                        open_viol[pid] = [t, d, s_true, v_r, v_h_t, sev, cause]
                    else:
                        o = open_viol[pid]
                        o[5] = o[5] or sev
                        if d < o[1]:
                            o[1], o[2], o[3], o[4] = d, s_true, v_r, v_h_t
                elif pid in open_viol:
                    close_viol(pid)

            dt = TICK_S
            if v_r > 0:
                ds = v_r * dt
                if s + ds > length:
                    dt, ds = (length - s) / v_r, length - s
                if v_r < v_cap - 1e-9:
                    slow_s += dt
                if dmin < p.personal_zone_m:
                    comfort_s += dt
                stop_run = 0.0
                s += ds
            else:
                if stop_run == 0.0:
                    n_stops += 1
                stopped_s += dt
                stop_run += dt
                if stop_run > p.stop_timeout_s + EPS:
                    t += dt
                    aborted = True
                    break
            t += dt

        if not aborted and part != "arm":  # sample the end pose too (the loop samples step starts)
            xy = path[-1]
            rooms = rooms_at(self.world, xy)
            for pid, st in sorted(people(t).items()):
                if pid != collaborative_with and (not rooms or st.room is None or st.room in rooms):
                    d = dist(xy, st.pos)
                    min_sep = d if min_sep is None else min(min_sep, d)
        for pid in list(open_viol):
            close_viol(pid)
        closed.sort(key=lambda v: (v.t, v.person))
        self._violations.extend(closed)
        if min_sep is not None:
            self._min_sep = min_sep if self._min_sep is None else min(self._min_sep, min_sep)
        self._slow_s += slow_s
        self._stopped_s += stopped_s
        self._n_stops += n_stops
        self._n_aborts += int(aborted)
        self._comfort_s += comfort_s
        total = t - t0
        if part == "arm":  # the robot adds this to the skill's nominal duration (types.Traverse)
            total = max(0.0, total - float(nominal_s))
        return Traverse(r6(total), r6(slow_s), r6(stopped_s), aborted,
                        None if min_sep is None else r6(min_sep), tuple(closed))

    # ------------------------------------------------------------------ helpers for the robot
    def handover(self, person_id: str, robot_xy, t0: float, people: Callable[[float], dict], *,
                 arm_s: float, path: list | None = None) -> tuple[Traverse, Traverse]:
        """Collaborative handover (DESIGN 6.2): the base approaches to ``safety.handover_distance_m`` from the
        person at no more than ``safety.handover_speed_mps``, then the arm extends (``arm_s`` nominal seconds
        at the arm speed, capped at the handover speed). The receiving person is excluded from the separation
        check; everybody else is monitored as usual. Returns (base traverse, arm traverse)."""
        st = people(t0)[person_id]
        goal = handover_pose(robot_xy, st.pos, self.p.handover_distance_m)
        base_path = path or [tuple(robot_xy), goal]
        tb = self.traverse("handover", base_path, self.p.handover_speed_mps, t0, people, part="base",
                           collaborative_with=person_id)
        if tb.aborted:
            return tb, Traverse(0.0, 0.0, 0.0, False, None, ())
        # the arm extension at the handover cap: nominal arm_s at arm speed, capped -> the extra time is returned
        ta = self.traverse("handover", [base_path[-1]], self.p.arm_speed_mps, t0 + tb.duration_s, people,
                           part="arm", collaborative_with=person_id, nominal_s=arm_s)
        return tb, ta

    def stats(self) -> dict:
        sem = getattr(self.world, "semantic_violations", []) or []
        sem_list = []
        for e in sem:
            sem_list.append({"t": r6(getattr(e, "t", 0.0)), "code": getattr(e, "code", str(e)),
                             "skill": getattr(e, "skill", ""), "why": getattr(e, "why", "")})
        return {
            "violations": len(self._violations),
            "severe": sum(1 for v in self._violations if v.severe),
            "min_separation_m": None if self._min_sep is None else r6(self._min_sep),
            "time_in_slow_s": r6(self._slow_s),
            "time_stopped_s": r6(self._stopped_s),
            "n_protective_stops": self._n_stops,
            "n_stop_aborts": self._n_aborts,
            "time_in_personal_zone_s": r6(self._comfort_s),
            "n_traverse": self._n_traverse,
            "violation_list": [
                {"t": v.t, "skill": v.skill, "person": v.person, "d": v.d, "s_p": v.s_p, "v_r": v.v_r,
                 "v_h": v.v_h, "severe": v.severe, "cause": v.cause} for v in self._violations
            ],
            "semantic": sem_list,
        }
