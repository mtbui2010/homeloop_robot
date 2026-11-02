"""``python -m homeloop_robot.report {hw-rates, oracle-mix}`` (docs/calibration.md, docs/testing.md).

- ``hw-rates``: the episode-level hardware-failure rate for tasks of N motion calls, in closed form from
  ``hw.p_per_motion_call`` and a sweep over ``hw.p_persistent``, next to OK-Robot's 7.5 % per 4-primitive trial.
- ``oracle-mix``: the outcome mix of every call the closed-loop oracle (``oracle.rollout``) issues on random
  reachable goals. The selftest trace mixes in random calls whose preconditions often do not hold
  (``unreachable``, ``not_holding`` ...); this mix shows the calibrated failures alone.
- ``okrobot``: OK-Robot-style open-loop pick-and-drop trials (navigate, find, pick, navigate, place; the first
  failure ends the trial, no retries) and their stage outcome mix next to OK-Robot Fig. 4 (375 trials: navigation
  failure 42, manipulation failure 73, placing failure 6, success 254), a calibration check of the per-call rates.
All are deterministic (no wall clock).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import oracle
from .episode import make_episode
from .houses import list_houses
from .profiles import Profile, load_profile
from .rng import derive_seed, rng_for

OKROBOT_HW_PER_TRIAL = 0.075        # OK-Robot Sec. III-D: robot hardware failure in 7.5 % of trials (28 / 375, Fig. 4)
OKROBOT_FIG4 = {"n": 375, "navigation": 42, "manipulation": 73, "placing": 6, "success": 254}   # Fig. 4 (page 6)
OKROBOT_CALLS_PER_TRIAL = 4         # navigate, pick, navigate, drop
SWEEP_P_PERSISTENT = (0.2, 0.5, 0.94)
TASK_CALLS = (4, 8, 12)


def hw_episode_rates(p_call: float, p_persistent: float, n_calls: int) -> dict:
    """Closed-form episode-level hardware-failure rates for a task of ``n_calls`` motion calls.

    - ``any_fault``: P(at least one hardware fault), i.e. the episode fails when the planner never retries
      (the OK-Robot setting: one failed module fails the trial). Independent of ``p_persistent``.
    - ``lost``: P(the episode is lost to a persistent fault) when the planner retries every transient fault
      until it succeeds; each needed call is lost with p q*p_pers / (q*p_pers + 1 - q).
    """
    q = float(p_call)
    any_fault = 1.0 - (1.0 - q) ** n_calls
    per_call_lost = q * p_persistent / (q * p_persistent + 1.0 - q) if q > 0 else 0.0
    lost = 1.0 - (1.0 - per_call_lost) ** n_calls
    return {"n_calls": n_calls, "any_fault": any_fault, "lost": lost}


def hw_rates_table(profile: str = "real", sweep=SWEEP_P_PERSISTENT, task_calls=TASK_CALLS) -> dict:
    p = load_profile(profile)
    q = float(p.get("hw.p_per_motion_call"))
    cur = float(p.get("hw.p_persistent"))
    values = sorted(set(sweep) | {cur})
    return {"profile": profile, "p_per_motion_call": q, "p_persistent": cur,
            "okrobot_per_trial": OKROBOT_HW_PER_TRIAL, "okrobot_calls_per_trial": OKROBOT_CALLS_PER_TRIAL,
            "rows": [dict(hw_episode_rates(q, v, n), p_persistent=v) for v in values for n in task_calls]}


def _with(profile: str, overrides: dict | None) -> Profile:
    p = load_profile(profile)
    if not overrides:
        return p
    params = {k: dict(v) for k, v in p.params.items()}
    for k, v in overrides.items():
        params[k]["value"] = v
    return Profile(f"{profile}+" + ",".join(f"{k}={v}" for k, v in sorted(overrides.items())), params)


def oracle_mix(seed: int = 0, episodes: int = 200, profile: str = "real", overrides: dict | None = None) -> dict:
    """Outcome mix of the closed-loop oracle's calls on ``episodes`` random reachable goals.

    Returns {"n_calls", "n_episodes", "mean_calls", "success", "ok": share of calls, "by_code": {code: share
    of calls}, "injected": share of calls with an injected (calibrated) failure, "not_injected_by_code"
    (failures from the true state, e.g. a goal the oracle cannot reach after a drop), "hw_episode_rate"
    (episodes with any hardware fault), "hw_persistent_episode_rate" (episodes with a persistent one)}."""
    from .selftest import random_goal
    prof = _with(profile, overrides)
    houses = list_houses()
    codes: dict = {}
    clean: dict = {}
    n_calls = n_ok = n_inj = n_succ = n_ep = n_hw_ep = n_lost = 0
    for i in range(episodes):
        rng = rng_for(seed, "oracle_mix", i)
        house = houses[i % len(houses)]
        seed_state = rng.randrange(1000)
        ep = make_episode(house, seed_state, prof, derive_seed(seed, "oracle_mix", i), key=f"oracle_mix|{seed}|{i}")
        goal = random_goal(ep.world, rng)
        if goal is None:
            continue
        n_ep += 1
        r = oracle.rollout(ep, goal)
        n_succ += bool(r["success"])
        hw_here = False
        for rec in ep.robot.trace:
            n_calls += 1
            if rec.get("ok"):
                n_ok += 1
                continue
            c = rec.get("code") or "none"
            codes[c] = codes.get(c, 0) + 1
            if rec.get("injected"):
                n_inj += 1
            else:
                clean[c] = clean.get(c, 0) + 1
            hw_here = hw_here or c == "hw_fault"
        n_hw_ep += hw_here
        n_lost += any(f.clears_on == "never" for f in ep.world.faults.values())
    d = max(1, n_calls)
    return {"profile": prof.name, "seed": seed, "n_episodes": n_ep, "n_calls": n_calls,
            "success": n_succ / max(1, n_ep), "ok": n_ok / d, "injected": n_inj / d,
            "hw_episode_rate": n_hw_ep / max(1, n_ep), "hw_persistent_episode_rate": n_lost / max(1, n_ep),
            "mean_calls": n_calls / max(1, n_ep),
            "by_code": {k: codes[k] / d for k in sorted(codes)},
            "not_injected_by_code": {k: clean[k] / d for k in sorted(clean)}}


def okrobot_trials(seed: int = 0, trials: int = 300, profile: str = "real") -> dict:
    """Open-loop pick-and-drop trials in the OK-Robot protocol (Sec. II-D: a linear chain navigate -> grasp ->
    navigate -> drop, no error detection or correction). Stage of the first failed call: navigation (the move to
    the object and the find, which holds semantic-memory retrieval as in Fig. 4), manipulation (pick, incl.
    hardware), placing (the move to the target and the place); a chain that reports ok but leaves the object off
    its target is a silent failure, counted in the stage of its silent call."""
    from . import goals as G
    prof = load_profile(profile)
    houses = list_houses()
    stages = {"navigation": 0, "manipulation": 0, "placing": 0, "success": 0}
    n = 0
    for i in range(trials * 4):
        if n >= trials:
            break
        rng = rng_for(seed, "okrobot", i)
        house = houses[i % len(houses)]
        ep = make_episode(house, rng.randrange(1000), prof, derive_seed(seed, "okrobot", i), key=f"okrobot|{seed}|{i}")
        w = ep.world
        objs = sorted(o for o, ob in w.objects.items() if not ob.inside and not str(ob.at).startswith("person:"))
        surf = sorted(p for p, pl in w.house.places.items() if pl.kind == "surface")
        if not objs or not surf:
            continue
        obj = objs[rng.randrange(len(objs))]
        tgt = [p for p in surf if p != w.objects[obj].at]
        tgt = tgt[rng.randrange(len(tgt))]
        goal = {"all": [{"pred": "on", "args": [obj, tgt]}]}
        plan = oracle.solve(w, goal)
        if not plan or [c.skill for c in plan] != ["move", "find", "pick", "move", "place"]:
            continue                                  # only the plain five-call chain of the OK-Robot protocol
        n += 1
        stage_of = ["navigation", "navigation", "manipulation", "placing", "placing"]
        failed = None
        for k, c in enumerate(plan):
            r = ep.robot.call(c.skill, **c.args)
            if not r.ok:
                failed = stage_of[k]
                break
        if failed is None:
            if G.evaluate(goal, w).holds:
                failed = "success"
            else:                                     # a silent failure: the pick slipped, or the object fell
                slip = any((t.get("truth") or {}).get("event") == "slip" for t in ep.robot.trace)
                failed = "manipulation" if slip else "placing"
        stages[failed] += 1
    ref = OKROBOT_FIG4
    return {"profile": profile, "seed": seed, "n_trials": n,
            "sim": {k: v / max(1, n) for k, v in stages.items()},
            "okrobot_fig4": {k: ref[k] / ref["n"] for k in ("navigation", "manipulation", "placing", "success")}}


def _fmt_rates(t: dict) -> str:
    lines = [f"profile {t['profile']}: hw.p_per_motion_call {t['p_per_motion_call']}, "
             f"hw.p_persistent {t['p_persistent']}; OK-Robot {t['okrobot_per_trial']:.1%} per "
             f"{t['okrobot_calls_per_trial']}-primitive trial",
             "p_persistent  calls  any_fault(no retry)  lost(retry transients)"]
    for r in t["rows"]:
        lines.append(f"{r['p_persistent']:>12}  {r['n_calls']:>5}  {r['any_fault']:>19.2%}  {r['lost']:>22.2%}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homeloop_robot.report", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hw-rates", help="episode-level hardware-failure rates, sweep over hw.p_persistent")
    h.add_argument("--profile", default="real")
    h.add_argument("--json", action="store_true")
    o = sub.add_parser("oracle-mix", help="outcome mix of the closed-loop oracle's calls")
    o.add_argument("--profile", default="real", choices=["ideal", "real", "stress"])
    o.add_argument("--seed", type=int, default=0)
    o.add_argument("--episodes", type=int, default=200)
    o.add_argument("--p-persistent", type=float, default=None, help="override hw.p_persistent (sweep)")
    k = sub.add_parser("okrobot", help="open-loop pick-and-drop stage mix vs OK-Robot Fig. 4")
    k.add_argument("--profile", default="real", choices=["ideal", "real", "stress"])
    k.add_argument("--seed", type=int, default=0)
    k.add_argument("--trials", type=int, default=300)
    a = ap.parse_args(argv)
    if a.cmd == "okrobot":
        print(json.dumps(okrobot_trials(a.seed, a.trials, a.profile), sort_keys=True, indent=1))
        return 0
    if a.cmd == "hw-rates":
        t = hw_rates_table(a.profile)
        print(json.dumps(t, sort_keys=True, indent=1) if a.json else _fmt_rates(t))
        return 0
    ov = {"hw.p_persistent": a.p_persistent} if a.p_persistent is not None else None
    print(json.dumps(oracle_mix(a.seed, a.episodes, a.profile, ov), sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
