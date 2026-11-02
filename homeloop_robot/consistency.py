"""Outcome consistency (DESIGN 13.3; docs/realism.md): ``python -m homeloop_robot.profiles consistency``.

1. Rates: for each skill / failure parameter of the ``real`` profile, N seeded calls (default 20,000) in
   the parameter's reference context; the empirical rate must not differ from the profile's rate at the
   0.1 % level (exact two-sided binomial test, i.e. inside the 99.9 % binomial interval).
2. Physical possibility: on random traces (oracle + random calls, every house, ideal / real / stress)
   no outcome may be impossible for the state it happened in: no `dropped` without holding, no
   `grasp_failed` outside pick / handover, no success effect after a failure, no `absent` for an
   object that is truly visible at the robot's place when perception is ideal, durations inside each
   skill's cited range.
3. The user model / ASR hooks (``user.consistency``, ``asr.consistency``) when they are installed.
"""

from __future__ import annotations

import importlib
import math
import sys
from dataclasses import dataclass

from .episode import make_episode
from .rng import Streams, r6, rng_for
from .types import FailureCode as F

Z_LEVEL = 0.001


# ── statistics ─────────────────────────────────────────────────────────────────────────────────────────

def _logpmf(k, n, p):
    if p <= 0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p)
            + (n - k) * math.log1p(-p))


def binom_two_sided_p(k: int, n: int, p: float) -> float:
    """Exact two-sided binomial p-value (sum of outcomes no more likely than k)."""
    if n == 0:
        return 1.0
    if p <= 0:
        return 1.0 if k == 0 else 0.0
    if p >= 1:
        return 1.0 if k == n else 0.0
    lk = _logpmf(k, n, p)
    mode = int((n + 1) * p)
    tot = 0.0
    # walk outwards from both ends only where pmf <= pmf(k); compute in a window for speed
    sd = math.sqrt(n * p * (1 - p))
    lo, hi = max(0, int(n * p - 12 * sd - 10)), min(n, int(n * p + 12 * sd + 10))
    for i in range(lo, hi + 1):
        li = _logpmf(i, n, p)
        if li <= lk + 1e-9:
            tot += math.exp(li)
    if k < lo or k > hi:
        tot += math.exp(lk)
    del mode
    return min(1.0, tot)


def interval(n: int, p: float, level: float = Z_LEVEL) -> tuple:
    """The central (1 - level) binomial interval of the count / n (normal approx, for reporting)."""
    z = 3.2905267 if level == 0.001 else 1.959964
    sd = math.sqrt(max(p * (1 - p), 0.0) / n) if n else 0.0
    return max(0.0, p - z * sd), min(1.0, p + z * sd)


@dataclass
class RateCheck:
    name: str
    param: str
    expected: float
    k: int = 0
    n: int = 0
    context: str = ""

    @property
    def rate(self):
        return self.k / self.n if self.n else float("nan")

    @property
    def p_value(self):
        return binom_two_sided_p(self.k, self.n, self.expected)

    @property
    def ok(self):
        return self.n > 0 and self.p_value >= Z_LEVEL

    def to_json(self):
        lo, hi = interval(self.n, self.expected)
        return {"name": self.name, "param": self.param, "expected": r6(self.expected), "k": self.k, "n": self.n,
                "rate": r6(self.rate) if self.n else None, "interval_999": [r6(lo), r6(hi)],
                "p_value": r6(self.p_value), "ok": self.ok, "context": self.context}


# ── a reusable episode with cheap state restore ──────────────────────────────────────────────────────

class Bench:
    def __init__(self, house: str, profile: str = "real"):
        self.ep = make_episode(house, 0, profile, 0, key="consistency", user_impl="null", safety_impl="null")
        self.w = self.ep.world
        self.robot = self.ep.robot
        self.prof = self.ep.profile

    def snap(self):
        w, r = self.w, self.w.robot
        return ({k: (o.at, o.inside) for k, o in w.objects.items()}, set(w.opened),
                (r.at, r.pose, r.holding, set(r.perceived), r.docked, r.estop, set(r.partial_open), set(r.phantoms)),
                dict(w.faults))

    def restore(self, s, key):
        w, r = self.w, self.w.robot
        objs, opened, rs, faults = s
        for k, (at, inside) in objs.items():
            w.objects[k].at, w.objects[k].inside = at, inside
        w.opened = set(opened)
        (r.at, r.pose, r.holding, perceived, r.docked, r.estop, partial, phantoms) = rs
        r.perceived, r.partial_open, r.phantoms = set(perceived), set(partial), set(phantoms)
        w.faults = dict(faults)
        w.utterances.clear()
        w.semantic_violations.clear()
        self.robot._reported_at = r.at
        self.robot._nth = {}
        self.robot.streams = Streams(0, key)

    def place_robot(self, pid):
        p = self.w.place(pid)
        r = self.w.robot
        r.at, r.pose, r.docked, r.perceived = pid, (p.pos[0], p.pos[1], p.yaw_deg), False, set()

    def put(self, oid, pid):
        o = self.w.objects[oid]
        o.at, o.inside = pid, self.w.place(pid).kind == "container"


def _ev(res):
    return res.truth.get("event")


def _hw(res):
    return res.code == F.HW_FAULT or (res.code == F.ESTOP)


def rate_checks(n: int = 20000, seed: int = 0) -> list:
    out = []

    def add(name, param, expected, context=""):
        c = RateCheck(name=name, param=param, expected=float(expected), context=context)
        out.append(c)
        return c

    # ── move ──
    b = Bench("family_house")
    p = b.prof
    targets = {"low": "tv_stand@living", "medium": "dining_table@kitchen", "high": "coffee_table@living"}
    hw = add("move hardware fault", "hw.p_per_motion_call", p.get("hw.p_per_motion_call"), "move dock -> place")
    pers = add("hardware fault persists", "hw.p_persistent", p.get("hw.p_persistent"), "given a move hw fault")
    split = add("move failure split: blocked", "move.split.blocked", p.get("move.split")["blocked"],
                "given a table failure")
    tmo = add("move timeout", "move.p_timeout", p.get("move.p_timeout"), "no hw fault, no table failure")
    fa = add("false arrival (normal target)", "move.p_false_arrival_normal", p.get("move.p_false_arrival_normal"),
             "successful move, hard_nav false")
    for clutter, tgt in targets.items():
        c = add(f"move fail, clutter {clutter}", f"move.p_fail.{clutter}", p.get("move.p_fail")[clutter], tgt)
        b.place_robot("dock@living")
        s = b.snap()
        per = n // 3 if clutter != "medium" else n - 2 * (n // 3)
        for i in range(per):
            b.restore(s, f"{seed}|move|{clutter}|{i}")
            res = b.robot.call("move", target=tgt)
            hw.n += 1
            if res.code == F.HW_FAULT:
                hw.k += 1
                pers.n += 1
                pers.k += _ev(res) == "hw_fault_persistent"
                continue
            if res.code == F.ESTOP:
                continue
            c.n += 1
            if _ev(res) in ("blocked", "unreachable"):
                c.k += 1
                split.n += 1
                split.k += _ev(res) == "blocked"
                continue
            tmo.n += 1
            if res.code == F.TIMEOUT:
                tmo.k += 1
                continue
            fa.n += 1
            fa.k += "false_arrival" in str(_ev(res) or "")
    # hard_nav target + transport drop
    hard = [pid for pid, pl in sorted(b.w.house.places.items()) if pl.hard_nav]
    fah = add("false arrival (hard target)", "move.p_false_arrival_hard", p.get("move.p_false_arrival_hard"),
              hard[0] if hard else "no hard_nav place")
    drop = add("drop in transit", "carry.p_drop", p.get("carry.p_drop"), "successful move while holding mug_1")
    if hard:
        b.place_robot("dock@living")
        s = b.snap()
        for i in range(n):
            b.restore(s, f"{seed}|movehard|{i}")
            res = b.robot.call("move", target=hard[0])
            if res.ok and res.code is None and _ev(res) != "timeout":
                fah.n += 1
                fah.k += "false_arrival" in str(_ev(res) or "")
    b.place_robot("dock@living")
    b.w.robot.holding = "mug_1"
    b.put("mug_1", "dock@living")
    b.w.objects["mug_1"].at = "robot"
    s = b.snap()
    for i in range(n):
        b.restore(s, f"{seed}|carry|{i}")
        res = b.robot.call("move", target="tv_stand@living")
        if res.ok:
            drop.n += 1
            drop.k += "drop" in res.truth
    # ── find ──
    b = Bench("senior_flat")
    p = b.prof
    hws = add("sensor hardware fault (find)", "hw.p_per_sensor_call", p.get("hw.p_per_sensor_call"), "find")
    unav = add("camera unavailable", "perception.p_unavailable", p.get("perception.p_unavailable"), "find, no hw")
    miss = add("find miss", "find.p_miss", p.get("find.p_miss"), "visible object, no confusable here")
    b.place_robot("nightstand@bedroom")       # glasses_1 visible, nothing confusable with glasses
    s = b.snap()
    for i in range(n):
        b.restore(s, f"{seed}|find|{i}")
        res = b.robot.call("find", obj="glasses_1")
        hws.n += 1
        if res.code == F.HW_FAULT:
            hws.k += 1
            continue
        unav.n += 1
        if res.code == F.PERCEPTION_UNAVAILABLE:
            unav.k += 1
            continue
        miss.n += 1
        miss.k += res.code == F.ABSENT
    for bucket, pid in (("few", "counter@kitchen"), ("many", None)):
        if pid is None:
            bb = Bench("family_house")
            pid, obj, other = "coffee_table@living", "mug_1", "mug_2"
        else:
            bb, obj, other = b, "mug_1", "mug_2"
        c = add(f"wrong instance ({bucket})", f"find.p_wrong_instance.{bucket}",
                bb.prof.get("find.p_wrong_instance")[bucket], f"{obj} with {other} at {pid}")
        bb.place_robot(pid)
        bb.put(obj, pid)
        bb.put(other, pid)
        s = bb.snap()
        for i in range(n):
            bb.restore(s, f"{seed}|wrong|{bucket}|{i}")
            res = bb.robot.call("find", obj=obj)
            if res.code is None and _ev(res) != "miss":
                c.n += 1
                c.k += _ev(res) == "wrong_instance"
            elif res.code == F.ABSENT and _ev(res) == "miss":
                pass
    fp = add("find false positive", "find.p_false_positive", p.get("find.p_false_positive"),
             "object elsewhere, other objects here")
    b2 = Bench("senior_flat")
    b2.place_robot("nightstand@bedroom")
    s = b2.snap()
    for i in range(n):
        b2.restore(s, f"{seed}|fp|{i}")
        res = b2.robot.call("find", obj="mug_1")
        if res.code in (F.HW_FAULT, F.PERCEPTION_UNAVAILABLE):
            continue
        fp.n += 1
        fp.k += _ev(res) == "false_positive"
    # ── pick ──
    b = Bench("senior_flat")
    p = b.prof
    for clutter, pid in (("low", "armchair@living"), ("medium", "counter@kitchen"), ("high", None)):
        if pid is None:
            bb, pid = Bench("family_house"), "coffee_table@living"
            obj = "remote_1"
        else:
            bb, obj = Bench("senior_flat"), "glasses_1" if clutter == "low" else "mug_1"
            bb.put(obj, pid)
        c = add(f"pick fail, clutter {clutter}", f"pick.p_fail.{clutter}", bb.prof.get("pick.p_fail")[clutter],
                f"{obj} at {pid}")
        silent = add(f"pick silent slip ({clutter})", "verify.p_false_success", bb.prof.get("verify.p_false_success"),
                     "successful pick") if clutter == "medium" else None
        bb.place_robot(pid)
        bb.w.robot.perceived = {obj}
        s = bb.snap()
        for i in range(n):
            bb.restore(s, f"{seed}|pick|{clutter}|{i}")
            res = bb.robot.call("pick", obj=obj)
            if res.code in (F.HW_FAULT, F.ESTOP):
                continue
            c.n += 1
            if _ev(res) == "pick_fail":
                c.k += 1
            elif silent is not None and res.ok:
                silent.n += 1
                silent.k += _ev(res) == "slip"
    for gclass, (house, obj, pid) in (("deformable", ("senior_flat", "towel_1", "wardrobe@bedroom")),
                                       ("light_deformable", ("senior_flat", "socks_1", "dresser@bedroom"))):
        bb = Bench(house)
        c = add(f"pick fail, {gclass}", f"pick.p_fail_class.{gclass}", bb.prof.get("pick.p_fail_class")[gclass],
                f"{obj} in open {pid}")
        bb.w.opened.add(pid)
        bb.place_robot(pid)
        bb.w.robot.perceived = {obj}
        s = bb.snap()
        for i in range(n):
            bb.restore(s, f"{seed}|pickc|{gclass}|{i}")
            res = bb.robot.call("pick", obj=obj)
            if res.code in (F.HW_FAULT, F.ESTOP):
                continue
            c.n += 1
            c.k += _ev(res) == "pick_fail"
    # pick split + retry success
    b = Bench("family_house")
    p = b.prof
    sp = add("pick failure split: absent", "pick.split.absent", p.get("pick.split")["absent"], "given a pick failure")
    rs = add("pick retry success", "pick.p_retry_success", p.get("pick.p_retry_success"),
             "second attempt after a failed pick")
    b.place_robot("coffee_table@living")
    b.w.robot.perceived = {"remote_1"}
    s = b.snap()
    for i in range(n * 2):
        b.restore(s, f"{seed}|picks|{i}")
        res = b.robot.call("pick", obj="remote_1")
        if _ev(res) != "pick_fail":
            continue
        sp.n += 1
        sp.k += res.code == F.ABSENT
        res2 = b.robot.call("pick", obj="remote_1")
        if res2.code in (F.HW_FAULT, F.ESTOP):
            continue
        rs.n += 1
        rs.k += res2.ok
    # ── place / open / close / handover ──
    b = Bench("senior_flat")
    p = b.prof
    pdrop = add("drop while placing", "place.p_drop", p.get("place.p_drop"), "place mug_1 on counter")
    fall = add("silent fall on place", "verify.p_false_success", p.get("verify.p_false_success"),
               "place reported ok")
    b.place_robot("counter@kitchen")
    b.w.robot.holding = "mug_1"
    b.w.objects["mug_1"].at = "robot"
    s = b.snap()
    for i in range(n):
        b.restore(s, f"{seed}|place|{i}")
        res = b.robot.call("place", target="counter@kitchen")
        if res.code in (F.HW_FAULT, F.ESTOP):
            continue
        pdrop.n += 1
        if res.code == F.DROPPED:
            pdrop.k += 1
            continue
        fall.n += 1
        fall.k += _ev(res) == "fall"
    for cls, pid in (("door", "fridge@kitchen"), ("drawer", "drawer@kitchen")):
        b = Bench("senior_flat")
        c = add(f"open fail ({cls})", f"open.p_fail.{cls}", p.get("open.p_fail")[cls], pid)
        rr = add(f"open retry success ({cls})", f"open.p_retry_success.{cls}", p.get("open.p_retry_success")[cls],
                 "second attempt")
        cc = add(f"close fail ({cls})", f"close.p_fail.{cls}", p.get("close.p_fail")[cls], pid)
        part = add(f"partial open ({cls})", "verify.p_false_success", p.get("verify.p_false_success"),
                   "open reported ok")
        b.place_robot(pid)
        s = b.snap()
        for i in range(n):
            b.restore(s, f"{seed}|open|{cls}|{i}")
            res = b.robot.call("open", container=pid)
            if res.code in (F.HW_FAULT, F.ESTOP):
                continue
            c.n += 1
            if _ev(res) == "open_fail":
                c.k += 1
                res2 = b.robot.call("open", container=pid)
                if res2.code not in (F.HW_FAULT, F.ESTOP):
                    rr.n += 1
                    rr.k += res2.ok
                continue
            part.n += 1
            part.k += _ev(res) == "partial_open"
        b.w.opened.add(pid)
        s = b.snap()
        for i in range(n):
            b.restore(s, f"{seed}|close|{cls}|{i}")
            res = b.robot.call("close", container=pid)
            if res.code in (F.HW_FAULT, F.ESTOP):
                continue
            cc.n += 1
            cc.k += _ev(res) == "close_fail"
        b.w.opened.discard(pid)
    b = Bench("senior_flat")
    osplit = add("open failure split: blocked", "open.split.blocked", p.get("open.split")["blocked"],
                 "given an open failure (drawer + door)")
    b.place_robot("fridge@kitchen")
    s = b.snap()
    for i in range(n * 2):
        b.restore(s, f"{seed}|osplit|{i}")
        res = b.robot.call("open", container="fridge@kitchen")
        if _ev(res) == "open_fail":
            osplit.n += 1
            osplit.k += res.code == F.BLOCKED
    b = Bench("senior_flat")
    hd = add("drop on handover", "handover.p_drop", p.get("handover.p_drop"), "handover mug_1 to grandma")
    b.w.robot.holding = "mug_1"
    b.w.objects["mug_1"].at = "robot"
    gpos = b.w.people["grandma"].pos
    r = b.w.robot
    r.at, r.pose = None, (gpos[0] + 1.2, gpos[1] + 0.3, 180.0)
    s = b.snap()
    for i in range(n):
        b.restore(s, f"{seed}|handover|{i}")
        res = b.robot.call("handover", person="grandma")
        if res.code in (F.HW_FAULT, F.ESTOP):
            continue
        hd.n += 1
        hd.k += res.code == F.DROPPED
    # ── checks ──
    b = Bench("senior_flat")
    p = b.prof
    fy = add("VLM false yes", "vlm.p_false_yes", p.get("vlm.p_false_yes"), "query false")
    fno = add("VLM false no", "vlm.p_false_no", p.get("vlm.p_false_no"), "query true")
    gw = add("grasp_check wrong", "grasp_check.p_wrong", p.get("grasp_check.p_wrong"), "hand empty")
    b.place_robot("counter@kitchen")
    s = b.snap()
    for i in range(n):
        b.restore(s, f"{seed}|vlm|{i}")
        res = b.robot.call("vlm_check", query="on(mug_1, stove@kitchen)")
        if res.ok and res.data.get("answer") in ("yes", "no"):
            fy.n += 1
            fy.k += res.data["answer"] == "yes"
        res = b.robot.call("vlm_check", query="on(mug_1, counter@kitchen)")
        if res.ok and res.data.get("answer") in ("yes", "no"):
            fno.n += 1
            fno.k += res.data["answer"] == "no"
        res = b.robot.call("grasp_check")
        if res.ok:
            gw.n += 1
            gw.k += res.data.get("holding") is True
    return out


# ── physical possibility on traces ─────────────────────────────────────────────────────────────────────

def _sig(w):
    return ({k: o.at for k, o in w.objects.items()}, frozenset(w.opened), w.robot.at, w.robot.holding,
            w.robot.docked)


def trace_checks(episodes: int = 24, calls: int = 40, seed: int = 0) -> dict:
    from . import oracle
    from .houses import list_houses
    from .selftest import random_call, random_goal
    viol = []
    counts = {"calls": 0}
    for prof in ("ideal", "real", "stress"):
        for i in range(episodes):
            house = list_houses()[i % len(list_houses())]
            rng = rng_for(seed, "trace", prof, i)
            ep = make_episode(house, rng.randrange(1000), prof, i, key=f"trace|{prof}|{i}", user_impl="null",
                              safety_impl="null")
            w, prof_obj = ep.world, ep.profile
            goal = random_goal(w, rng)
            for _ in range(calls):
                call = None
                if goal and rng.random() < 0.6:
                    plan = oracle.solve(w, goal)
                    if plan:
                        call = (plan[0].skill, dict(plan[0].args))
                if call is None:
                    call = random_call(w, rng)
                skill, args = call
                before = _sig(w)
                held = w.robot.holding
                here = w.robot.at
                visible = set(w.visible_at(here)) if here else set()
                res = ep.robot.call(skill, **args)
                counts["calls"] += 1
                after = _sig(w)
                where = f"{prof}/{house}/ep{i}/{skill}({args})"
                if res.code == F.DROPPED and held is None:
                    viol.append({"check": "dropped_without_holding", "where": where})
                if res.code == F.GRASP_FAILED and skill not in ("pick", "handover"):
                    viol.append({"check": "grasp_failed_outside_pick", "where": where})
                if not res.ok and before != after:
                    allowed = res.code == F.DROPPED and held is not None and after[3] is None \
                        and after[0][held].startswith("floor@")
                    if not allowed:
                        viol.append({"check": "effect_after_failure", "where": where, "code": res.code.value})
                if prof == "ideal" and res.code == F.ABSENT and skill in ("find", "pick"):
                    oid = w.resolve_object(args.get("obj", ""), None)
                    if isinstance(oid, str) and oid in visible and not (skill == "pick" and held is not None):
                        viol.append({"check": "absent_but_visible", "where": where})
                bad = _duration_bad(skill, args, res, prof_obj)
                if bad:
                    viol.append({"check": "duration_out_of_range", "where": where, "why": bad})
    by = {}
    for v in viol:
        by[v["check"]] = by.get(v["check"], 0) + 1
    return {"calls": counts["calls"], "violations": len(viol), "by_check": by, "examples": viol[:20]}


def _duration_bad(skill, args, res, prof) -> str:
    d = res.duration_s
    if res.code == F.SOFTWARE:
        return "" if d == 0 else f"software error took {d} s"
    if not res.ok:
        return "" if d >= 0 else "negative duration"
    rng = {"find": "find.duration_s", "look": "look.duration_s", "vlm_check": "vlm.duration_s",
           "open": "open.duration_s", "close": "close.duration_s", "dock": "dock.duration_s"}
    if skill in rng and d > 0:
        lo, hi = prof.get(rng[skill])
        if not (lo - 1e-6 <= d <= hi + 1e-6):
            return f"{d:.3f} s outside {rng[skill]} [{lo}, {hi}]"
    if skill in ("pick", "place", "put_in") and d > 0:
        lo, hi = prof.get("pick_place.duration_s")
        if not (lo / 2 - 1e-6 <= d <= hi / 2 + 1e-6):
            return f"{d:.3f} s outside half of pick_place.duration_s [{lo / 2}, {hi / 2}]"
    if skill == "wait" and abs(d - float(args.get("seconds", 0))) > 1e-6:
        return f"wait took {d} s"
    return ""


# ── user / ASR hooks ───────────────────────────────────────────────────────────────────────────────────

def hook_checks(n: int, seed: int) -> list:
    out = []
    for mod, fn, call in (("user", "consistency", lambda f: f(_world(), _real(), n, seed, "en")),
                          ("user", "consistency", lambda f: f(_world(), _real(), n, seed, "ko")),
                          ("asr", "consistency", lambda f: f(_real(), n, seed))):
        name = f"homeloop_robot.{mod}"
        try:
            m = importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name == name:
                out.append({"hook": f"{mod}.{fn}", "status": "not installed", "ok": True})
                continue
            raise
        f = getattr(m, fn, None)
        if f is None:
            out.append({"hook": f"{mod}.{fn}", "status": "missing", "ok": False})
            continue
        r = call(f)
        out.append({"hook": f"{mod}.{fn}", "status": "ran", "ok": _hook_ok(r), "result": r})
    return out


def _hook_ok(r) -> bool:
    if isinstance(r, bool):
        return r
    if isinstance(r, dict):
        for k in ("ok", "passed", "pass"):
            if k in r:
                return bool(r[k])
        for k in ("violations", "failures", "failed"):
            if k in r:
                v = r[k]
                return not v
        return all(_hook_ok(v) for v in r.values() if isinstance(v, (dict, bool)))
    if isinstance(r, (list, tuple)):
        return all(_hook_ok(x) for x in r)
    return True


def _world():
    from .world import from_house
    return from_house("senior_flat", 0)


def _real():
    from .profiles import load_profile
    return load_profile("real")


# ── command ────────────────────────────────────────────────────────────────────────────────────────────

def run(n: int = 20000, seed: int = 0, strict: bool = False, out=print, episodes: int = 24) -> int:
    import json
    checks = rate_checks(n, seed)
    fails = 0
    out(f"== outcome rates: {len(checks)} checks, {n} calls each (0.1 % two-sided binomial test)")
    for c in checks:
        j = c.to_json()
        status = "PASS" if c.ok else "FAIL"
        fails += not c.ok
        out(f"{status}  {c.name:38s} {c.param:34s} expected {j['expected']:<9} observed {j['k']}/{j['n']} = "
            f"{j['rate'] if j['rate'] is not None else 'n/a'}  99.9% [{j['interval_999'][0]}, {j['interval_999'][1]}]"
            f"  p={j['p_value']}")
    tr = trace_checks(episodes=episodes, seed=seed)
    st = "PASS" if tr["violations"] == 0 else "FAIL"
    fails += tr["violations"] > 0
    out(f"{st}  physical possibility on {tr['calls']} traced calls: {tr['violations']} violation(s) {tr['by_check']}")
    for v in tr["examples"]:
        out(f"        {json.dumps(v, ensure_ascii=False, sort_keys=True)}")
    for h in hook_checks(min(n, 5000), seed):
        st = "PASS" if h["ok"] else "FAIL"
        fails += not h["ok"]
        out(f"{st}  hook {h['hook']}: {h['status']}")
        if h.get("result") is not None and not h["ok"]:
            out(f"        {json.dumps(h['result'], ensure_ascii=False, sort_keys=True, default=str)[:2000]}")
    out(f"== consistency: {fails} failed check(s)")
    return 1 if fails else 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m homeloop_robot.consistency")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    return run(a.n, a.seed, a.strict)


if __name__ == "__main__":
    sys.exit(main())
