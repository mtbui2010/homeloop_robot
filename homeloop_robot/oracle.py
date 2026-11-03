"""The oracle: a plan of skill calls from the TRUE world to a goal (docs/oracle.md).

``solve(world, goal)`` reads exact locations, open / partly-open containers, what the robot holds and
the active faults, and returns the calls that reach the goal in the ``ideal`` profile, or None when the
goal cannot be reached (heavy / fixed object, a container that does not open, a person not in the
house, a semantic hazard, an object out of reach, or more than ``max_calls`` calls). Deterministic:
ties are broken by id.
"""

from __future__ import annotations

import importlib
from typing import Optional

from . import goals as G
from .catalog import CLASSES, MESSAGE_TEXT
from .types import Call
from .world import World, dist

HIGH_SHELF_REACH_M = 1.5
PERSON_STANDOFF_M = 1.2     # move.person_standoff_m of the profiles (WALTERS05, docs/calibration.md)


class Unsolvable(Exception):
    pass


def _hazards():
    try:
        return importlib.import_module("homeloop_robot.hazards")
    except ModuleNotFoundError as e:
        if e.name == "homeloop_robot.hazards":
            return None
        raise


class _Plan:
    """A plan under construction over a symbolic copy of the world."""

    def __init__(self, world: World, lang: str, people_pos: Optional[dict] = None):
        self.w = world.copy()
        self.people_pos = dict(people_pos or {})
        if people_pos:
            # the delivery goal and reach read people_now: plan from where people are now
            now = dict(self.w.people_now)
            for pid, xy in people_pos.items():
                if pid in self.w.people:
                    old = now.get(pid) or {}
                    moving = bool(old.get("moving")) and tuple(old.get("pos", ())) == tuple(xy)
                    now[pid] = {"pos": (float(xy[0]), float(xy[1])), "moving": moving}
            self.w.people_now = now
        self.calls: list = []
        self.cost = 0.0
        self.lang = lang

    # effects of the planned calls on the copy (ideal profile: every call succeeds)
    def move(self, pid: str):
        w, r = self.w, self.w.robot
        if r.at == pid:
            return
        dst = w.place(pid).pos
        self.cost += w.path_length(r.pose[:2], dst)
        self.calls.append(Call("move", {"target": pid}))
        r.at, r.pose, r.perceived, r.docked = pid, (dst[0], dst[1], w.place(pid).yaw_deg), set(), False

    def person_pos(self, person: str) -> tuple:
        return tuple(self.people_pos.get(person) or self.w.people[person].pos)

    def move_person(self, person: str):
        w, r = self.w, self.w.robot
        ppos = self.person_pos(person)
        from .skills import ARRIVED_EPS_M, person_stop_xy
        sp = person_stop_xy(w, ppos, PERSON_STANDOFF_M)
        if r.at is None and dist(r.pose[:2], sp) <= ARRIVED_EPS_M:
            return                                   # already at the person's stop point
        self.cost += w.path_length(r.pose[:2], sp)
        self.calls.append(Call("move", {"target": person}))
        r.at, r.pose, r.perceived, r.docked = None, (sp[0], sp[1], 0.0), set(), False

    def open(self, cid: str):
        w = self.w
        if cid in w.opened and cid not in w.robot.partial_open:
            return
        pl = w.place(cid)
        if pl.kind != "container" or not pl.container.openable:
            raise Unsolvable(f"{cid} cannot be opened")
        self.empty_hand_check()
        self.move(cid)
        if cid in w.robot.partial_open:          # reported open but only partly: close, then open again
            self.calls.append(Call("close", {"container": cid}))
            w.opened.discard(cid)
            w.robot.partial_open.discard(cid)
        self.calls.append(Call("open", {"container": cid}))
        w.opened.add(cid)

    def close(self, cid: str):
        w = self.w
        if cid not in w.opened:
            return
        self.empty_hand_check()
        self.move(cid)
        self.calls.append(Call("close", {"container": cid}))
        w.opened.discard(cid)
        w.robot.partial_open.discard(cid)

    def empty_hand_check(self):
        if self.w.robot.holding is not None:
            raise Unsolvable("internal: hand must be empty here")

    def fetch(self, oid: str):
        w, r = self.w, self.w.robot
        o = w.objects[oid]
        if r.holding == oid:
            return
        if r.holding is not None:
            self.stow_held()
        if o.at.startswith("person:"):
            raise Unsolvable(f"{oid} is held by {o.at[7:]}")
        c = CLASSES[o.cls]
        if not c.liftable:
            raise Unsolvable(f"{oid} ({o.cls}) is too heavy or fixed to pick up")
        loc = o.at
        pl = w.place(loc)
        if "high_shelf" in pl.tags and pl.height_m > HIGH_SHELF_REACH_M:
            raise Unsolvable(f"{oid} is on {loc}, out of the arm's reach")
        if pl.kind == "container":
            self.open(loc)
        self.move(loc)
        if oid not in r.perceived:
            self.calls.append(Call("find", {"obj": oid}))
            r.perceived.add(oid)
        self.calls.append(Call("pick", {"obj": oid}))
        r.holding, o.at, o.inside = oid, "robot", False
        r.perceived.discard(oid)

    def put(self, pid: str):
        w, r = self.w, self.w.robot
        oid = r.holding
        pl = w.place(pid)
        if w.free_slots(pid) <= 0:
            raise Unsolvable(f"{pid} is full")
        self.move(pid)
        if pl.kind == "container":
            if pid not in w.opened or pid in r.partial_open:
                raise Unsolvable(f"internal: {pid} must be open before put_in")
            self.calls.append(Call("put_in", {"container": pid}))
        else:
            self.calls.append(Call("place", {"target": pid}))
        o = w.objects[oid]
        o.at, o.inside, r.holding = pid, pl.kind == "container", None

    def stow_held(self):
        """Put a held object that no goal needs back where it came from, or on the nearest surface
        with room (a container only when it is open)."""
        w, r = self.w, self.w.robot
        oid = r.holding
        cands = []
        home = w.initial_at.get(oid)
        for pid, pl in sorted(w.house.places.items()):
            if pl.kind in ("floor", "dock") or w.free_slots(pid) <= 0:
                continue
            if pl.kind == "container" and (pid not in w.opened or pid in r.partial_open):
                continue
            if "high_shelf" in pl.tags and pl.height_m > HIGH_SHELF_REACH_M:
                continue
            if _place_hazard(w, oid, pid):
                continue
            pri = 0 if pid == home else 1
            cands.append((pri, w.path_length(r.pose[:2], pl.pos), pid))
        if not cands:
            raise Unsolvable(f"nowhere to put {oid} down")
        self.put(sorted(cands)[0][2])


def _place_hazard(world, oid, pid) -> bool:
    hz = _hazards()
    if hz is None:
        return False
    try:
        return bool(hz.check_call(world, "place", {"obj": oid, "target": pid}))
    except Exception:                               # noqa: BLE001 - a hazard-module bug must not hide plans
        return False


def _atom_objs(a) -> list:
    return [x for x in a.get("args", [])[:1]] if a.get("pred") in ("on", "in", "held_by", "delivered", "holding") \
        else []


def _pending_into(plan: _Plan, place: str, oid: str) -> int:
    """How many of the goal's on / in atoms still have to put an object (other than ``oid``) onto ``place``."""
    n = 0
    for a in getattr(plan, "atoms", ()):
        if a.get("pred") in ("on", "in") and len(a.get("args") or []) == 2 and a["args"][1] == place \
                and a["args"][0] != oid and not G.holds(a, plan.w):
            n += 1
    return n


def _apply(plan: _Plan, a: dict):
    """Add the calls that make atom ``a`` true (plan.w tracks the effects)."""
    w, r = plan.w, plan.w.robot
    if G.holds(a, w):
        return
    if "not" in a:
        inner = a["not"]
        p = inner.get("pred")
        if p == "open":
            return plan.close(inner["args"][0])
        if p == "closed":
            return plan.open(inner["args"][0])
        if p == "holding" or p == "hand_empty":
            if p == "hand_empty":
                raise Unsolvable("goal needs the hand to hold something unspecified")
            return plan.stow_held()
        if p == "docked":
            return plan.move(_first_non_dock(w))
        raise Unsolvable(f"cannot plan for 'not {p}'")
    if "any" in a:
        best = None
        for i, alt in enumerate(a["any"]):
            trial = _Plan(w, plan.lang, plan.people_pos)
            try:
                _apply(trial, alt)
            except Unsolvable:
                continue
            key = (trial.cost, len(trial.calls), i)
            if best is None or key < best[0]:
                best = (key, alt)
        if best is None:
            raise Unsolvable("no alternative of any(...) can be reached")
        return _apply(plan, best[1])
    p, args = a["pred"], a.get("args") or []
    if p == "on":
        oid, pid = args
        if r.holding not in (None, oid):
            plan.stow_held()
        plan.fetch(oid)
        plan.put(pid)
    elif p == "in":
        oid, cid = args
        if r.holding not in (None, oid):
            plan.stow_held()
        if w.objects[oid].at != cid:
            if r.holding == oid and (cid not in w.opened or cid in r.partial_open):
                plan.stow_held()                     # the container needs an empty hand to open
            plan.open(cid)
            plan.fetch(oid)
            plan.put(cid)
    elif p == "held_by":
        oid, person = args
        if person not in w.people:
            raise Unsolvable(f"{person} is not in the house")
        if r.holding not in (None, oid):
            plan.stow_held()
        plan.fetch(oid)
        plan.move_person(person)
        plan.calls.append(Call("handover", {"person": person}))
        o = w.objects[oid]
        o.at, r.holding = f"person:{person}", None
    elif p == "delivered":
        # the atom's mode is the oracle's own choice (see _own_modes), never the task's label
        oid, person = args
        if person not in w.people:
            raise Unsolvable(f"{person} is not in the house")
        if r.holding not in (None, oid):
            plan.stow_held()
        surface = None
        if a.get("mode") == "reach":
            for s in _reach().reachable_surfaces(w, person, free_only=True):
                # leave room for the goal's own on / in atoms that still need this surface
                if not _place_hazard(w, oid, s) and w.free_slots(s) > _pending_into(plan, s, oid):
                    surface = s
                    break
        plan.fetch(oid)
        if surface is not None:
            plan.put(surface)
        else:
            plan.move_person(person)
            plan.calls.append(Call("handover", {"person": person}))
            o = w.objects[oid]
            o.at, r.holding = f"person:{person}", None
    elif p == "holding":
        plan.fetch(args[0])
    elif p == "hand_empty":
        plan.stow_held()
    elif p == "open":
        if r.holding is not None:
            plan.stow_held()
        plan.open(args[0])
    elif p == "closed":
        if r.holding is not None:
            plan.stow_held()
        plan.close(args[0])
    elif p == "robot_at":
        plan.move(args[0])
    elif p == "docked":
        plan.move(w.house.dock)
        plan.calls.append(Call("dock", {}))
        r.docked = True
    elif p == "said_to":
        person, key = args
        if person not in w.people:
            raise Unsolvable(f"{person} is not in the house")
        plan.move_person(person)
        text = MESSAGE_TEXT[key][plan.lang]
        plan.calls.append(Call("say", {"text": text, "lang": plan.lang}))
        from .types import Utterance
        w.utterances.append(Utterance(t=0.0, skill="say", text=text, lang=plan.lang, heard_by=(person,)))
    elif p == "unmoved":
        raise Unsolvable(f"{args[0]} was moved; it cannot be put back exactly")
    else:
        raise Unsolvable(f"unknown predicate {p}")


def _first_non_dock(w) -> str:
    return sorted(pid for pid, p in w.house.places.items() if p.kind == "surface")[0]


def _order(world: World, atoms: list) -> list:
    """Object atoms nearest-first (greedy by path length), then messages, then open/closed atoms,
    then robot_at / docked / hand_empty; holding() goals last so the hand stays free."""
    obj_atoms, msg, art, final, hold = [], [], [], [], []
    for a in atoms:
        base = a.get("not", a)
        p = base.get("pred")
        if "any" in a:
            obj_atoms.append(a)
        elif p in ("on", "in", "held_by", "delivered") and "not" not in a:
            obj_atoms.append(a)
        elif p == "holding" and "not" not in a:
            hold.append(a)
        elif p == "said_to":
            msg.append(a)
        elif p in ("open", "closed"):
            art.append(a)
        else:
            final.append(a)
    out = []
    # greedy from a fixed point (the robot's start pose), not the current pose: re-solving after every
    # call must give the same order, or the plan would switch between atoms (ping-pong)
    pos = tuple(world.place(world.house.robot_start).pos)
    held = world.robot.holding
    todo = list(obj_atoms)
    while todo:
        def key(a):
            objs = _atom_objs(a) or _atom_objs(a["any"][0]) if "any" in a else _atom_objs(a)
            oid = objs[0] if objs else None
            if oid is None:
                return (1, 0.0, G.format_atom(a))
            if oid == held:
                return (0, 0.0, G.format_atom(a))
            o = world.objects[oid]
            if o.at in world.house.places:
                return (1, world.path_length(pos, world.place(o.at).pos), G.format_atom(a))
            return (1, 1e9, G.format_atom(a))
        todo.sort(key=key)
        a = todo.pop(0)
        out.append(a)
        objs = _atom_objs(a)
        if objs and len(a.get("args", [])) > 1 and a["pred"] in ("on", "in"):
            dst = a["args"][1]
            if dst in world.house.places:
                pos = world.place(dst).pos
        held = None
    out = _free_first(world, out)
    return out + msg + art + final + hold


def _free_first(world: World, atoms: list) -> list:
    """Move an object off a full place before another atom puts something onto that place (a full nightstand:
    take the phone away first, then put the book there). Stable otherwise."""
    out = list(atoms)
    for _ in range(len(out)):
        changed = False
        for i, a in enumerate(out):
            if a.get("pred") not in ("on", "in") or len(a.get("args") or []) != 2:
                continue
            dst = a["args"][1]
            if dst not in world.house.places or world.free_slots(dst) > 0:
                continue
            for j in range(i + 1, len(out)):
                b = out[j]
                objs = _atom_objs(b)
                if objs and b.get("pred") in ("on", "in", "held_by", "delivered") and objs[0] in world.objects \
                        and world.objects[objs[0]].at == dst and not (len(b.get("args") or []) > 1 and b["args"][1] == dst):
                    out.insert(i, out.pop(j))
                    changed = True
                    break
            if changed:
                break
        if not changed:
            break
    return out


def _reach():
    from . import reach
    return reach


def delivery_modes(world: World, goal: dict, *, text: str = "", lang: str = "en",
                   people_pos: Optional[dict] = None) -> dict:
    """{(obj, person): "reach" | "hand"} for every delivery atom of ``goal``, chosen the way a robot would from
    what it observes when it gets the request (``reach.choose_mode``: the words, the house profile, the
    furniture around the person where they are). The atoms' own ``mode`` labels are never read. A runner calls
    this once at the start and passes the result to every ``solve`` of the episode."""
    w = _Plan(world, lang, people_pos).w
    out = {}
    for a in G.iter_preds(goal):
        if a.get("pred") == "delivered" and len(a.get("args") or []) == 2 and a["args"][1] in w.people:
            out[(a["args"][0], a["args"][1])] = _reach().choose_mode(w, a["args"][1], text, lang).mode
    return out


def _own_modes(atom: dict, modes: dict):
    """A copy of ``atom`` whose delivery atoms carry the oracle's mode instead of the task's label."""
    if "not" in atom:
        return {"not": _own_modes(atom["not"], modes)}
    if "any" in atom:
        return {"any": [_own_modes(x, modes) for x in atom["any"]]}
    if atom.get("pred") == "delivered":
        args = list(atom.get("args") or [])
        return {"pred": "delivered", "args": args, "mode": modes.get(tuple(args), "hand")}
    return atom


def solve(world: World, goal: dict, *, avoid_hazards: bool = True, max_calls: int = 60,
          lang: str = "en", people_pos: Optional[dict] = None, text: Optional[str] = None,
          modes: Optional[dict] = None) -> Optional[list]:
    """Calls that reach ``goal`` from the true state of ``world``; None when it cannot be reached.
    ``people_pos`` ({person: (x, y)}, e.g. from ``user.people_at(t)``) overrides the start positions
    of people who have moved. Deliveries: ``modes`` ({(obj, person): reach | hand}, from
    :func:`delivery_modes` at the start of the episode) or, when not given, :func:`delivery_modes` on the
    request ``text`` now. Reach: put the object on the nearest reachable support surface with room (a
    handover when there is none any more); hand: a handover. The goal's ``mode`` labels are never read."""
    try:
        return _solve(world, goal, avoid_hazards=avoid_hazards, max_calls=max_calls, lang=lang,
                      people_pos=people_pos, text=text, modes=modes)
    except Unsolvable:
        return None


def _solve(world, goal, *, avoid_hazards, max_calls, lang, people_pos=None, text=None, modes=None) -> list:
    if any(a.get("pred") == "delivered" for a in G.iter_preds(goal)):
        if modes is None:
            modes = delivery_modes(world, goal, text=text or "", lang=lang, people_pos=people_pos)
        goal = dict(goal, all=[_own_modes(a, modes) for a in goal.get("all") or []])
    if G.validate(goal, world):
        raise Unsolvable("invalid goal: " + "; ".join(G.validate(goal, world)))
    if avoid_hazards:
        hz = _hazards()
        if hz is not None and hz.goal_hazards(world, goal):
            raise Unsolvable("the goal needs a hazard: " + ", ".join(hz.goal_hazards(world, goal)))
    plan = _Plan(world, lang, people_pos)
    atoms = list(goal.get("all") or [])
    plan.atoms = atoms
    for a in _order(world, atoms):
        _apply(plan, a)
    # later atoms can undo earlier ones (e.g. a container closed and reopened): one more pass
    for a in _order(plan.w, atoms):
        if not G.holds(a, plan.w):
            _apply(plan, a)
    ev = G.evaluate({"all": atoms}, plan.w)
    if not ev.holds:
        raise Unsolvable("plan does not reach: " + ", ".join(s for s, h in ev.atoms if not h))
    if len(plan.calls) > max_calls:
        raise Unsolvable(f"needs {len(plan.calls)} calls > {max_calls}")
    return plan.calls


def explain_unsolvable(world: World, goal: dict, *, avoid_hazards: bool = True, max_calls: int = 60,
                       text: Optional[str] = None, lang: str = "en") -> str:
    """Why ``solve`` returns None ("" when the goal is solvable)."""
    try:
        _solve(world, goal, avoid_hazards=avoid_hazards, max_calls=max_calls, lang=lang, text=text)
    except Unsolvable as e:
        return str(e)
    return ""


HELP_QUESTION = {"en": "Could you please clear the way for me?", "ko": "지나갈 수 있게 길을 좀 비켜 주시겠어요?"}
RETRY_WAIT_S = 5


def recovery_call(code: Optional[str], skill: str, world: World, user, t: float, lang: str = "en") -> Optional[Call]:
    """The closed-loop oracle's follow-up to a failed call (shared by :func:`rollout` and the bench's
    ``oracle`` planner, so the calibration report and the benchmark use one policy): a blocked move ->
    ask the user to clear the way when the user can hear the robot, else wait; perception_unavailable /
    blocked (other skills) -> wait 5 s; anything else -> None (retry or re-plan)."""
    if code == "blocked" and skill == "move":
        uid = getattr(user, "user_id", None)
        xy = tuple(world.robot.pose[:2])
        reach = getattr(user, "reachable", None)
        if uid is not None and (reach(xy, t) if callable(reach) else
                                hasattr(user, "hears") and user.hears(uid, xy, t, False)):
            return Call("ask", {"question": HELP_QUESTION.get(lang, HELP_QUESTION["en"]), "lang": lang,
                                "meaning": {"qtype": "help"}})
        return Call("wait", {"seconds": RETRY_WAIT_S})
    if code in ("perception_unavailable", "blocked"):
        return Call("wait", {"seconds": RETRY_WAIT_S})
    return None


def rollout(episode, goal: dict, *, max_calls: int = 60, max_time_s: float = 1800.0, max_attempts: int = 3,
            lang: str = "en", text: Optional[str] = None) -> dict:
    """Closed-loop oracle on an episode (reference behaviour, docs/oracle.md): re-solve from the true
    world after every call; at most ``max_attempts`` consecutive failures of the same call; the follow-up of
    :func:`recovery_call` (wait 5 s before retrying perception_unavailable / blocked; ask for help with a
    blocked path when the user can hear). Returns {"success", "calls", "status"}."""
    w, robot = episode.world, episode.robot
    fails: dict = {}
    n = 0
    people = {pid: st.pos for pid, st in episode.user.people_at(episode.clock.t).items()}
    modes = delivery_modes(w, goal, text=text or "", lang=lang, people_pos=people)
    while n < max_calls and episode.clock.t < max_time_s:
        if G.evaluate(goal, w).holds:
            return {"success": True, "calls": n, "status": "done"}
        people = {pid: st.pos for pid, st in episode.user.people_at(episode.clock.t).items()}
        plan = solve(w, goal, lang=lang, people_pos=people, modes=modes)
        if not plan:
            return {"success": False, "calls": n, "status": "give_up"}
        c = plan[0]
        key = (c.skill, tuple(sorted(c.args.items())))
        if fails.get(key, 0) >= max_attempts:
            return {"success": False, "calls": n, "status": "give_up"}
        r = robot.call(c.skill, **c.args)
        n += 1
        if r.ok:
            fails.pop(key, None)
            continue
        fails[key] = fails.get(key, 0) + 1
        if r.code is not None and r.code.value in ("hw_fault", "estop") and \
                any(f.clears_on == "never" for f in w.faults.values()) or w.robot.estop:
            return {"success": False, "calls": n, "status": "give_up"}
        rc = recovery_call(r.code.value if r.code is not None else None, c.skill, w, episode.user,
                           episode.clock.t, lang)
        if rc is not None and n < max_calls:
            robot.call(rc.skill, **rc.args)
            n += 1
    return {"success": bool(G.evaluate(goal, w).holds), "calls": n, "status": "budget"}
