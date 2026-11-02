"""``python -m homeloop_robot.selftest --seed N --episodes K --profile P --out FILE`` (docs/testing.md).

Writes a JSONL trace of skill calls on random houses: per episode, 25 calls, each with p 0.6 the next
oracle call toward a random reachable goal, else a random skill with random valid arguments. One line
per call, then one summary line per episode. Same arguments -> a byte-identical file.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import goals as G
from . import oracle
from .catalog import CLASSES, MESSAGE_TEXT, MESSAGES
from .episode import make_episode
from .houses import list_houses
from .rng import derive_seed, r6, rng_for
from .skills import SKILL_SPECS
from .types import _round_tree

CALLS_PER_EPISODE = 25
P_ORACLE = 0.6


def _dumps(obj) -> str:
    return json.dumps(_round_tree(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _liftable(w, oid) -> bool:
    o = w.objects[oid]
    if not CLASSES[o.cls].liftable or o.at not in w.house.places:
        return False
    pl = w.place(o.at)
    return not ("high_shelf" in pl.tags and pl.height_m > oracle.HIGH_SHELF_REACH_M)


def random_atom(w, rng) -> dict:
    """One random goal atom over the world (it may already hold or be unsolvable)."""
    places = w.house.places
    objs = sorted(o for o in w.objects if _liftable(w, o))
    surfaces = sorted(p for p, pl in places.items() if pl.kind in ("surface", "seat")
                      and not ("high_shelf" in pl.tags and pl.height_m > oracle.HIGH_SHELF_REACH_M))
    conts = sorted(p for p, pl in places.items() if pl.kind == "container" and pl.container.openable)
    people = sorted(w.people)
    kind = rng.choices(["on", "in", "held_by", "open", "closed", "said_to", "robot_at", "docked"],
                       weights=[30, 20, 12, 8, 8, 8, 8, 6])[0]
    if kind == "on":
        return {"pred": "on", "args": [rng.choice(objs), rng.choice(surfaces)]}
    if kind == "in":
        return {"pred": "in", "args": [rng.choice(objs), rng.choice(conts)]}
    if kind == "held_by":
        return {"pred": "held_by", "args": [rng.choice(objs), rng.choice(people)]}
    if kind in ("open", "closed"):
        return {"pred": kind, "args": [rng.choice(conts)]}
    if kind == "said_to":
        return {"pred": "said_to", "args": [rng.choice(people), rng.choice(sorted(MESSAGES))]}
    if kind == "robot_at":
        return {"pred": "robot_at", "args": [rng.choice(surfaces + conts)]}
    return {"pred": "docked", "args": []}


def random_goal(w, rng, *, max_atoms: int = 3, tries: int = 50, lang: str = "en"):
    """A random goal that does not hold yet and that the oracle can reach (None after ``tries``)."""
    for _ in range(tries):
        n = rng.choice([x for x in (1, 1, 2, 2, 3) if x <= max_atoms])
        atoms, seen = [], set()
        for _ in range(n):
            a = random_atom(w, rng)
            key = (a["pred"], a["args"][0] if a["args"] else "")
            if key in seen or (a["pred"] in ("open", "closed") and any(k[1] == a["args"][0] for k in seen)):
                continue
            seen.add(key)
            atoms.append(a)
        g = {"all": atoms}
        if not atoms or G.validate(g, w) or G.evaluate(g, w).holds:
            continue
        # objects may appear in one object atom only
        objs = [a["args"][0] for a in atoms if a["pred"] in ("on", "in", "held_by")]
        if len(objs) != len(set(objs)):
            continue
        if oracle.solve(w, g, lang=lang) is not None:
            return g
    return None


def random_call(w, rng):
    places = sorted(w.house.places)
    objs = sorted(w.objects)
    people = sorted(w.people)
    skill = rng.choice(sorted(SKILL_SPECS))
    if skill == "move":
        return skill, {"target": rng.choice(places + people)}
    if skill in ("find", "pick"):
        return skill, {"obj": rng.choice(objs)}
    if skill == "place":
        return skill, {"target": rng.choice(places)}
    if skill in ("put_in", "open", "close"):
        return skill, {"container": rng.choice(places)}
    if skill == "handover":
        return skill, {"person": rng.choice([""] + people)}
    if skill in ("say", "announce"):
        k = rng.choice(sorted(MESSAGE_TEXT))
        return skill, {"text": MESSAGE_TEXT[k]["en"], "lang": "en"}
    if skill == "ask":
        return skill, {"question": "Where should I put it?", "lang": "en"}
    if skill == "vlm_check":
        return skill, {"query": G.format_atom(random_atom(w, rng))}
    if skill == "wait":
        return skill, {"seconds": rng.choice([2, 5, 10])}
    return skill, {}


def run(seed: int, episodes: int, profile: str, out_path: str) -> int:
    houses = list_houses()
    lines = []
    for i in range(episodes):
        rng = rng_for(seed, "selftest", i)
        house = houses[i % len(houses)]
        seed_state = rng.randrange(1000)
        ep = make_episode(house, seed_state, profile, derive_seed(seed, "selftest", i),
                          key=f"selftest|{seed}|{i}")
        w = ep.world
        goal = random_goal(w, rng)
        codes = {}
        n_ok = 0
        for k in range(CALLS_PER_EPISODE):
            call = None
            if goal is not None and G.evaluate(goal, w).holds:
                goal = random_goal(w, rng)
            if goal is not None and rng.random() < P_ORACLE:
                plan = oracle.solve(w, goal)
                if plan:
                    call = (plan[0].skill, dict(plan[0].args))
            if call is None:
                call = random_call(w, rng)
            skill, args = call
            res = ep.robot.call(skill, **args)
            n_ok += res.ok
            if res.code is not None:
                codes[res.code.value] = codes.get(res.code.value, 0) + 1
            rec = ep.robot.trace[-1]
            lines.append(_dumps({"ep": i, "house": house, "seed_state": seed_state, "k": k, "skill": skill,
                                 "args": rec["args"], "ok": res.ok, "code": rec["code"],
                                 "injected": res.injected, "t": rec["t"], "dur": rec["dur"],
                                 "data": rec["data"], "truth": rec["truth"]}))
        st = ep.safety.stats() if hasattr(ep.safety, "stats") else {}
        summary = {"house": house, "seed_state": seed_state, "goal": G.format(goal) if goal else None,
                   "goal_holds": bool(goal and G.evaluate(goal, w).holds), "n_ok": n_ok,
                   "n_fail": CALLS_PER_EPISODE - n_ok, "codes": dict(sorted(codes.items())),
                   "sim_time_s": r6(ep.clock.t), "semantic_violations": len(w.semantic_violations),
                   "safety": {k: st.get(k) for k in ("violations", "severe", "min_separation_m",
                                                     "n_protective_stops") if k in st},
                   "profile": profile, "profile_sha": ep.profile.sha}
        lines.append(_dumps({"ep": i, "summary": summary}))
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homeloop_robot.selftest", description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--profile", default="real", choices=["ideal", "real", "stress"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    return run(a.seed, a.episodes, a.profile, a.out)


if __name__ == "__main__":
    sys.exit(main())
