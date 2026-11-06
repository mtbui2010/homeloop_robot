"""The mock robot: every household skill, checked against the TRUE world (docs/skills.md).

``Robot.call(skill, **args)`` is the one entry point. Per call:
(1) validate args against :data:`SKILL_SPECS` (software error, no time spent);
(2) global states: e-stop -> motion skills fail ``estop``; a persistent fault on the skill's device ->
    ``hw_fault``; (3) a pending user interruption -> the motion call is ``cancelled``;
(4) true-state preconditions (deterministic, ``injected=False``); (5) the failure model
    (outcomes.py, ``injected=True``); (6) effects on the true world; (7) simulated duration.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import math
import re
from typing import Optional

from . import goals as _goals
from .catalog import CLASSES
from .outcomes import U, Ctx, container_class, sample_outcome, split_code, uniforms
from .rng import r6
from .types import FailureCode, FaultState, SkillResult, SkillSpec, UserEvent, Utterance
from .world import dist

F = FailureCode
# words a description may end with that name the object's packaging, not another object (a "milk pack" is the milk
# carton; a "milk glass" is not): general English / Korean packaging nouns (design choice)
PACKAGING = {"en": ("pack", "packet", "carton", "bottle", "box", "bag", "jar", "can", "tin", "tub", "container", "case"),
             "ko": ("팩", "통", "병", "상자", "박스", "봉지", "캔", "곽")}


def detector_hits(world, query) -> list:
    """The objects a free-text detector query names (sorted ids): a catalog name / alias of the object is in the
    query as whole words (EN) or a part of it (KO, no spaces after norm), the query ends with that name or a
    packaging noun (PACKAGING), and no colour word in the query contradicts the object's colour."""
    from .catalog import COLORS
    from .world import LANGS, norm
    q = norm(query)
    if not q:
        return []
    qw = q.split()
    said_cols = {k for k, v in COLORS.items() for lg in LANGS
                 if (re.search(rf"(?<!\w){re.escape(norm(v[lg]))}(?!\w)", q) if lg == "en" else norm(v[lg]) in q)}
    out = []
    for oid in sorted(world.objects):
        o = world.objects[oid]
        c = CLASSES[o.cls]
        col = o.attrs.get("color")
        if col and said_cols and col not in said_cols:
            continue
        hit = False
        for lg in LANGS:
            for n in [c.name[lg]] + list((c.aliases or {}).get(lg) or []):
                nn = norm(n)
                if not nn:
                    continue
                if lg == "en":
                    nw = nn.split()
                    hit = set(nw) <= set(qw) and (qw[-1] in nw or qw[-1] in PACKAGING["en"])
                else:
                    hit = nn in q and (q.endswith(nn) or any(q.endswith(nn + p) for p in PACKAGING["ko"]))
                if hit:
                    break
            if hit:
                break
        if hit:
            out.append(oid)
    return out


PRECONDITION_S = 1.0          # simulated time of a call that fails a true-state precondition (design choice)
HANDOVER_RANGE_M = 3.0        # handover("") looks for the nearest person within this distance
HANDOVER_TIMEOUT_DEFAULT_S = 60.0   # time spent when a handover is not taken and the user model gives no latency
POSE_AT_TOL_M = 0.3           # pose() reports `at` within this distance of an approach pose
HIGH_SHELF_REACH_M = 1.5      # a high_shelf place higher than this is out of the arm's reach
WAIT_CLEARS_S = 5.0           # a wait at least this long may clear a camera fault
DOCK_TRAVEL_M = 0.5           # the base reverses this far onto the charger contacts (design choice)
# an ask that is a request for help with an obstacle (any language the robot speaks)
HELP_RX = re.compile(r"\b(clear|block\w*|in the way|out of the way|get (past|through)|let me (pass|through)|"
                     r"path|obstacle)\b|비켜|치워|치우|길|막혀|지나가|지나갈", re.I)
# calls that do not change what the robot is doing between a blocked move and the ask about it
_QUIET = ("wait", "look", "say", "announce", "pose", "grasp_check", "vlm_check")

MOTION_SKILLS = ("move", "pick", "place", "put_in", "open", "close", "handover", "dock")


def _spec(name, params, required, desc, motion, device):
    return SkillSpec(name=name, params=params, required=tuple(required), description=desc, motion=motion,
                     device=device)


_S = {"type": "string"}
SKILL_SPECS: dict = {s.name: s for s in [
    _spec("move", {"target": _S}, ["target"], "Drive to a place (id or name) or to a person.", True, "base"),
    _spec("find", {"obj": _S}, ["obj"], "Look for an object at the current place.", False, "camera"),
    _spec("pick", {"obj": _S}, ["obj"], "Pick up an object found at the current place.", True, "arm"),
    _spec("place", {"target": _S}, ["target"], "Put the held object on the place the robot is at.", True, "arm"),
    _spec("put_in", {"container": _S}, ["container"], "Put the held object into the open container here.", True, "arm"),
    _spec("open", {"container": _S}, ["container"], "Open a container (drawer, cabinet, fridge ...) here.", True, "arm"),
    _spec("close", {"container": _S}, ["container"], "Close a container here.", True, "arm"),
    _spec("handover", {"person": {"type": "string", "default": ""}}, [],
          "Hand the held object to a person nearby ('' = the nearest person).", True, "arm"),
    _spec("say", {"text": _S, "lang": {"type": "string", "default": "en"}}, ["text"],
          "Say a sentence to the people in this room.", False, "speaker"),
    _spec("announce", {"text": _S, "lang": {"type": "string", "default": "en"}}, ["text"],
          "Announce a sentence to this room and the adjacent rooms.", False, "speaker"),
    _spec("ask", {"question": _S, "lang": {"type": "string", "default": "en"},
                  "meaning": {"type": "object", "default": None}}, ["question"],
          "Ask a question and listen for the answer. meaning (optional): the question's structured form, "
          "{qtype, slots} (docs/user_model.md); the user hears the question text.", False, "speaker"),
    _spec("look", {}, [], "Describe what the camera sees here: objects, containers, people.", False, "camera"),
    _spec("vlm_check", {"query": _S}, ["query"],
          "Ask the camera whether a condition holds, e.g. 'on(mug_1, table@kitchen)'.", False, "camera"),
    _spec("wait", {"seconds": {"type": "number"}}, ["seconds"], "Wait 0 < seconds <= 120.", False, "none"),
    _spec("dock", {}, [], "Dock at the charging dock (the robot must be at the dock).", True, "base"),
    _spec("grasp_check", {}, [], "Read the gripper sensor: is something held?", False, "gripper"),
    _spec("pose", {}, [], "Read the localization pose.", False, "base"),
]}

_NOT_IN_KEY = ("meaning",)
_SENSOR_DEVICE_SKILLS = ("find", "look", "vlm_check", "say", "announce", "ask", "grasp_check", "pose")


def standoff_point(path: list, stand: float) -> tuple:
    """The point ``stand`` metres before the end of a polyline (measured along it)."""
    left = stand
    for i in range(len(path) - 1, 0, -1):
        a, b = path[i - 1], path[i]
        seg = dist(a, b)
        if seg >= left and seg > 0:
            k = (seg - left) / seg
            return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
        left -= seg
    return tuple(path[0])


ARRIVED_EPS_M = 0.05          # a move to a person ends at once when the base is already this close to its stop point


def person_stop_xy(world, ppos, stand: float) -> tuple:
    """Where a move to a person at ``ppos`` stops: ``stand`` metres before them on the path from the charging
    dock (the way into their room). One point per person position, whatever room the robot comes from, so the
    robot_agent ENV entry of a person (configs/tasks.env_for) is where this move really ends and its arrival
    check (arrive_tol) can be met. The person is not on the robot's safety list during the move
    (``collaborative_with``), as before."""
    dock = world.house.places[world.house.dock].pos
    return standoff_point(world.path((float(dock[0]), float(dock[1])), tuple(ppos)), stand)


def canon_args(args: dict) -> str:
    return json.dumps({k: args[k] for k in sorted(args)}, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str)


def _hazards():
    try:
        return importlib.import_module("homeloop_robot.hazards")
    except ModuleNotFoundError as e:
        if e.name == "homeloop_robot.hazards":
            return None
        raise


def _uniform(u: float, rng_pair) -> float:
    lo, hi = float(rng_pair[0]), float(rng_pair[1])
    return lo + (hi - lo) * u


class _Res:
    """Mutable result under construction."""

    def __init__(self):
        self.ok = True
        self.code = None
        self.msg = "ok"
        self.data = {}
        self.dur = 0.0
        self.injected = False
        self.truth = {"effect": True}

    def fail(self, code, msg, *, injected=False, dur=None, effect=False, event=None):
        self.ok, self.code, self.msg, self.injected = False, code, msg, injected
        if dur is not None:
            self.dur = dur
        self.truth["effect"] = effect
        if event:
            self.truth["event"] = event
        return self


class Robot:
    def __init__(self, world, profile, streams, clock, user, safety, lang: str = "en"):
        self.world = world
        self.profile = profile
        self.streams = streams
        self.clock = clock
        self.user = user
        self.safety = safety
        self.lang = lang
        self.trace: list = []
        self.events: list = []               # every user event delivered (interruptions)
        self.pending_events: list = []       # delivered since the last pop_events()
        self.n_calls = 0
        self._idle_run_s = 0.0       # time waited without a skill call (idle), since the last skill call
        self.idle_total_s = 0.0
        self._n_idle_clears = 0
        self.n_motion = 0
        self._nth: dict = {}
        self._interrupts: list = []          # (after_motion_calls, UserEvent)
        self._events_t = 0.0
        self._reported_at = world.robot.at   # what the robot believes (false arrivals differ)
        self.believed_holding = None         # from its own reports (a silent slip differs from the truth)
        self.believed_opened = set(world.opened)
        self.sync_people()

    # ── public ──────────────────────────────────────────────────────────────────────────────────────
    def schedule_interrupt(self, after_motion_calls: int, event: UserEvent) -> None:
        """The runner arms a scripted interruption: motion call number ``after_motion_calls + 1``
        returns ``cancelled`` and ``event`` is delivered (DESIGN 5.5)."""
        self._interrupts.append((int(after_motion_calls), event))
        self._interrupts.sort(key=lambda x: x[0])

    def sync_people(self) -> None:
        """Copy where people are now (the user model at the clock's time) into ``world.people_now``, which the
        delivery goal and ``reach`` read. Called after every call; a runner that lets time pass otherwise calls
        it before judging."""
        now = {}
        people_at = getattr(self.user, "people_at", None)
        if people_at is None:
            return
        for pid, st in sorted((people_at(self.clock.t) or {}).items()):
            v = tuple(getattr(st, "vel", (0.0, 0.0)) or (0.0, 0.0))
            now[pid] = {"pos": (float(st.pos[0]), float(st.pos[1])), "moving": bool(v[0] or v[1])}
        self.world.people_now = now
        # the robot's perception: a person in the robot's room is seen there now; anyone else keeps the position
        # they were last seen at (world.people_seen; docs/robot_agent.md "people tracking")
        here = set(self.world.rooms_of(self.world.robot.pose[:2]))
        for pid, st in now.items():
            if here and set(self.world.rooms_of(st["pos"])) & here:
                self.world.people_seen[pid] = tuple(st["pos"])

    def pop_events(self) -> list:
        ev, self.pending_events = self.pending_events, []
        return ev

    def observe(self) -> dict:
        r = self.world.robot
        rng = self.streams.rng_for("observe", self.n_calls)
        sig = float(self.profile.get("pose.sigma_m"))
        x, y, yaw = r.pose
        return {"pose_est": [r6(x + rng.gauss(0, sig) if sig else x), r6(y + rng.gauss(0, sig) if sig else y),
                             r6(yaw)],
                "at": self._reported_at, "holding_sensor": r.holding is not None, "estop": r.estop,
                "health": self.health()}

    def health(self) -> dict:
        out = {}
        for dev in ("base", "arm", "camera", "gripper", "speaker"):
            f = self.world.faults.get(dev)
            out[dev] = "ok" if f is None else f"{f.code.value}:{f.clears_on}"
        out["estop"] = self.world.robot.estop
        out["ok"] = all(v == "ok" for k, v in out.items() if k not in ("estop", "ok")) and not self.world.robot.estop
        return out

    @property
    def reported_at(self):
        return self._reported_at

    def idle(self, seconds: float) -> float:
        """The robot waits ``seconds`` without calling a skill (a control loop sleeping between sensor polls): simulated
        time passes, and a wait of at least ``WAIT_CLEARS_S`` in a row has the effect of the ``wait`` skill on a camera
        fault that clears on waiting. The same for every robot (consistency fix, not a change of rates). Returns the
        seconds that passed."""
        dt = max(0.0, float(seconds))
        if dt <= 0.0:
            return 0.0
        self.clock.advance(dt)
        self.idle_total_s += dt
        self._idle_run_s += dt
        f = self.world.faults.get("camera")
        if f is not None and f.clears_on == "wait" and self._idle_run_s >= WAIT_CLEARS_S:
            self._idle_run_s = 0.0
            u = uniforms(self.streams.rng_for("outcome", "idle", self._n_idle_clears))
            self._n_idle_clears += 1
            if u[U.FAIL] < f.p_clear:
                del self.world.faults["camera"]
        self.sync_people()
        return dt

    def call(self, skill: str, /, **args) -> SkillResult:
        t0 = self.clock.t
        self._idle_run_s = 0.0
        res = self._call(skill, args, t0)
        dur = max(0.0, float(res.dur))
        self.clock.advance(dur)
        out = SkillResult(ok=res.ok, code=res.code, msg=res.msg, data=res.data, duration_s=dur,
                          injected=res.injected, truth=res.truth)
        rec = {"k": self.n_calls, "skill": skill, "args": {k: args[k] for k in sorted(args)}, "t": r6(t0),
               "dur": r6(dur)}
        rec.update(out.to_json())
        self.trace.append(rec)
        self._update_belief(skill, out)
        self.sync_people()
        return out

    def _update_belief(self, skill: str, out: SkillResult) -> None:
        d = out.data
        if out.ok:
            if skill == "pick":
                self.believed_holding = d.get("holding")
            elif skill in ("place", "put_in", "handover"):
                self.believed_holding = None
            elif skill == "open" and d.get("opened"):
                self.believed_opened.add(d["opened"])
            elif skill == "close" and d.get("closed"):
                self.believed_opened.discard(d["closed"])
        elif out.code == F.DROPPED:
            self.believed_holding = None

    @property
    def believed(self) -> dict:
        """The robot's own belief (from its reports), as an adapter would track it."""
        return {"at": self._reported_at, "holding": self.believed_holding,
                "opened": sorted(self.believed_opened)}

    # ── dispatch ────────────────────────────────────────────────────────────────────────────────────
    def _call(self, skill, args, t0) -> _Res:
        self.n_calls += 1
        res = _Res()
        spec = SKILL_SPECS.get(skill)
        if spec is None:
            return res.fail(F.SOFTWARE, f"NameError: skill {skill!r} is not defined")
        err = self._check_args(spec, args)
        if err:
            return res.fail(F.SOFTWARE, err)
        full = {k: args.get(k, v.get("default")) for k, v in spec.params.items()}
        # the outcome draws do not depend on an ask's structured meaning (the same question gets the same draws)
        key = (skill, canon_args({k: v for k, v in full.items() if k not in _NOT_IN_KEY}))
        nth = self._nth.get(key, 0)
        self._nth[key] = nth + 1
        u = uniforms(self.streams.rng_for("outcome", skill, key[1], nth))
        self._u = u
        w = self.world
        # (2) global states
        if spec.motion and w.robot.estop:
            return res.fail(F.ESTOP, "e-stop pressed: the robot cannot move until it is reset")
        f = w.faults.get(spec.device)
        if f is not None and f.code == F.HW_FAULT and f.clears_on == "never":
            return res.fail(F.HW_FAULT, f"hardware fault: {spec.device} motor" if spec.device in ("base", "arm")
                            else f"hardware fault: {spec.device}", dur=PRECONDITION_S)
        # (3) interruptions
        if spec.motion:
            self.n_motion += 1
            ev = self._take_interrupt(t0)
            if ev is not None:
                res.data["event"] = {"kind": ev.kind, "text": ev.text}
                return res.fail(F.CANCELLED, "cancelled by the user", dur=0.5, event="interrupt")
        else:
            self._poll_user_events(t0)
        # random e-stop during this motion call
        if spec.motion:
            rate = float(self.profile.get("estop.rate_per_h"))
            est = self._nominal_s(skill, full)
            if rate > 0 and u[U.ESTOP] < 1.0 - math.exp(-rate * est / 3600.0):
                w.robot.estop = True
                return res.fail(F.ESTOP, "e-stop pressed during the motion", injected=True,
                                dur=est * u[U.FAILTIME], event="estop")
        handler = getattr(self, f"_sk_{skill}")
        return handler(res, u, t0, **full)

    def _check_args(self, spec: SkillSpec, args: dict) -> Optional[str]:
        extra = sorted(set(args) - set(spec.params))
        if extra:
            return f"TypeError: {spec.name}() got an unexpected keyword argument {extra[0]!r}"
        miss = [p for p in spec.required if p not in args]
        if miss:
            return f"TypeError: {spec.name}() missing 1 required positional argument: {miss[0]!r}"
        for k, v in args.items():
            t = spec.params[k].get("type")
            if t == "string" and not isinstance(v, str):
                return f"TypeError: {spec.name}() argument {k!r} must be a string, got {type(v).__name__}"
            if t == "object" and v is not None and not isinstance(v, dict):
                return f"TypeError: {spec.name}() argument {k!r} must be a dict, got {type(v).__name__}"
            if t == "number":
                try:
                    float(v)
                except (TypeError, ValueError):
                    return f"TypeError: {spec.name}() argument {k!r} must be a number, got {v!r}"
        return None

    def _take_interrupt(self, t0) -> Optional[UserEvent]:
        ev = None
        if self._interrupts and self.n_motion == self._interrupts[0][0] + 1:
            _, ev = self._interrupts.pop(0)
            ev = dataclasses.replace(ev, t=t0)
        for e in self._poll_user_events(t0):
            if ev is None and e.kind in ("stop", "correction"):
                ev = e
        if ev is not None and ev not in self.events:
            self.events.append(ev)
            self.pending_events.append(ev)
        return ev

    def _poll_user_events(self, t0) -> list:
        if t0 <= self._events_t:
            return []
        evs = list(self.user.events_between(self._events_t, t0) or [])
        self._events_t = t0
        out = []
        for e in evs:
            if e.kind not in ("stop", "correction"):
                self.events.append(e)
                self.pending_events.append(e)
            out.append(e)
        return out

    # ── helpers ─────────────────────────────────────────────────────────────────────────────────────
    def _p(self, name):
        return self.profile.get(name)

    def _xy(self):
        return tuple(self.world.robot.pose[:2])

    def _nominal_s(self, skill, args) -> float:
        p = self._p
        if skill == "move":
            return 30.0
        if skill in ("pick", "place", "put_in"):
            a, b = p("pick_place.duration_s")
            return (a + b) / 4.0
        if skill in ("open", "close", "handover", "dock"):
            a, b = p(f"{skill}.duration_s")
            return (a + b) / 2.0
        return 1.0

    def _hw(self, res, u, device, motion=None) -> bool:
        """Rule 1: hardware fault on this call. True when it fired (res failed). The rate is the motion-call rate
        for a base / arm primitive (navigate, pick, drop: how the published rate was counted) and the sensor-call
        rate for a reading (``motion=False``: the pose read after a move is a sensor call on the base)."""
        motion = device in ("base", "arm") if motion is None else motion
        pr = float(self._p("hw.p_per_motion_call" if motion else "hw.p_per_sensor_call"))
        if u[U.HW] < pr:
            persistent = u[U.HW_PERSIST] < float(self._p("hw.p_persistent"))
            if persistent:
                self.world.faults[device] = FaultState(device=device, code=F.HW_FAULT, since_t=self.clock.t,
                                                       clears_on="never", p_clear=0.0)
            name = f"{device} motor" if motion else device
            res.fail(F.HW_FAULT, f"hardware fault: {name}", injected=True,
                     event="hw_fault_persistent" if persistent else "hw_fault")
            return True
        return False

    def _camera_down(self, res, u) -> bool:
        w = self.world
        f = w.faults.get("camera")
        if f is not None and f.clears_on == "wait":
            res.fail(F.PERCEPTION_UNAVAILABLE, "camera unavailable (no fresh frame)", injected=True,
                     dur=PRECONDITION_S, event="camera_down")
            return True
        if self._hw(res, u, "camera"):
            res.dur = PRECONDITION_S
            return True
        if u[U.UNAVAIL] < float(self._p("perception.p_unavailable")):
            w.faults["camera"] = FaultState(device="camera", code=F.PERCEPTION_UNAVAILABLE, since_t=self.clock.t,
                                            clears_on="wait", p_clear=float(self._p("perception.p_clear_on_wait")))
            res.fail(F.PERCEPTION_UNAVAILABLE, "camera unavailable (no fresh frame)", injected=True,
                     dur=PRECONDITION_S, event="camera_down")
            return True
        return False

    def _resolve_obj(self, name):
        """What the camera / grasp skills look for: the object's catalog name or alias (exact), else a detector
        query naming it with extra words, as an open-vocabulary detector reads a description (``detector_hits``:
        "white milk pack" finds the milk carton; milestone 5 round 1, KO hl-dev-000003)."""
        oid = self.world.resolve_object(name, None)
        if oid is not None:
            return oid
        hits = detector_hits(self.world, name)
        return None if not hits else hits[0] if len(hits) == 1 else hits

    def _floor_of(self, xy) -> str:
        rid = self.world.room_of(xy) or sorted(self.world.house.rooms)[0]
        return f"floor@{rid}"

    def _drop_held(self, xy) -> str:
        r = self.world.robot
        oid = r.holding
        o = self.world.objects[oid]
        o.at = self._floor_of(xy)
        o.inside = False
        r.holding = None
        return o.at

    def _record_hazards(self, skill, args):
        hz = _hazards()
        if hz is None:
            return []
        evs = list(hz.check_call(self.world, skill, dict(args)) or [])
        out = []
        for e in evs:
            if hasattr(e, "t"):
                e = dataclasses.replace(e, t=self.clock.t)
            self.world.semantic_violations.append(e)
            out.append(e)
        return out

    def _people(self):
        return self.user.people_at

    def _arm_safety(self, res, skill, collaborative_with=None, nominal_s=None) -> bool:
        """Arm motion under the safety monitor for its whole nominal duration (``res.dur`` when not given):
        extra time from slow-downs and stops, abort -> blocked. True when aborted."""
        ns = float(res.dur if nominal_s is None else nominal_s)
        tr = self.safety.traverse(skill, [self._xy()], float(self._p_arm_speed()), self.clock.t, self._people(),
                                  part="arm", collaborative_with=collaborative_with, nominal_s=ns)
        res.dur += float(tr.duration_s)
        if tr.aborted:
            res.fail(F.BLOCKED, "protective stop: person in the way (blocked)", injected=True, event="safety_abort")
            return True
        return False

    def _p_arm_speed(self):
        return self.profile.get("safety.arm_speed_mps", 0.4)

    def _here(self, res, pid) -> bool:
        if self.world.robot.at != pid:
            res.fail(F.UNREACHABLE, f"cannot reach {pid} from here", dur=PRECONDITION_S)
            return False
        return True

    def _resolve_place_or_fail(self, res, name) -> Optional[str]:
        pid = self.world.resolve_place(name, None)
        if pid is None:
            res.fail(F.UNREACHABLE, f"cannot reach {name}: unknown place", dur=PRECONDITION_S)
            return None
        if isinstance(pid, list):
            res.fail(F.UNREACHABLE, f"cannot reach {name}: ambiguous, which one of {', '.join(pid)}?",
                     dur=PRECONDITION_S)
            res.data["candidates"] = pid
            return None
        return pid

    # ── skills ──────────────────────────────────────────────────────────────────────────────────────
    def _sk_move(self, res, u, t0, target):
        w, r = self.world, self.world.robot
        person = None
        pid = w.resolve_place(target, None)
        if pid is None:
            person = w.resolve_person(target, None)
            if isinstance(person, list):
                res.data["candidates"] = person
                return res.fail(F.UNREACHABLE, f"cannot reach {target}: ambiguous person", dur=PRECONDITION_S)
            if person is None:
                return res.fail(F.UNREACHABLE, f"cannot reach {target}: unknown place", dur=PRECONDITION_S)
        elif isinstance(pid, list):
            res.data["candidates"] = pid
            return res.fail(F.UNREACHABLE, f"cannot reach {target}: ambiguous, which one of {', '.join(pid)}?",
                            dur=PRECONDITION_S)
        if pid is not None and r.at == pid:
            res.data["at"] = pid
            return res
        if pid is not None:
            pl = w.place(pid)
            goal, yaw = tuple(pl.pos), pl.yaw_deg
            clutter, hard, tags, tkey = pl.clutter, pl.hard_nav, tuple(pl.tags), pid
        else:
            pst = self.user.people_at(t0).get(person)
            ppos = tuple(pst.pos) if pst else tuple(w.people[person].pos)
            here = self._xy()
            stand = float(self._p("move.person_standoff_m"))
            goal = person_stop_xy(w, ppos, stand)
            if dist(here, goal) <= ARRIVED_EPS_M:
                res.data["at"] = f"person:{person}"
                return res
            yaw = math.degrees(math.atan2(ppos[1] - goal[1], ppos[0] - goal[0]))
            clutter, hard, tags, tkey = "medium", False, (), f"person:{person}"
        path = w.path(self._xy(), goal)
        speed = float(self._p("move.speed_mps"))
        length = sum(dist(path[i], path[i + 1]) for i in range(len(path) - 1))
        nominal = length / speed if speed > 0 else 0.0
        frac = _uniform(u[U.FAILTIME], self._p("move.fail_time_frac"))
        if self._hw(res, u, "base"):
            res.dur = nominal * frac
            return res
        fkey = f"path:{tkey}"
        fault = w.faults.get(fkey)
        ctx = Ctx(skill="move", clutter=clutter, hard_nav=hard, tags=tags)
        if fault is not None:                                   # a retry of a blocked move
            if u[U.FAIL] < fault.p_clear:
                del w.faults[fkey]
                res.truth["event"] = "blocked_cleared"
            else:
                stuck = "carpet" in tags
                return res.fail(F.BLOCKED, "stuck on the carpet" if stuck else "path blocked", injected=True,
                                dur=nominal * frac, event="blocked_persists")
        else:
            out = sample_outcome(self.profile, ctx, u)
            if out.kind == "fail":
                if out.code == F.BLOCKED:
                    carpet = "carpet" in tags
                    w.faults[fkey] = FaultState(
                        device=fkey, code=F.BLOCKED, since_t=t0, clears_on="retry",
                        p_clear=float(self._p("move.p_stuck_retry_success" if carpet else "move.p_retry_clears_blocked")),
                        p_help=float(self._p("move.p_help_clears_blocked")))
                    return res.fail(F.BLOCKED, "stuck on the carpet" if carpet else "path blocked", injected=True,
                                    dur=nominal * frac, event="blocked")
                return res.fail(F.UNREACHABLE, f"cannot reach {tkey}: localization lost", injected=True,
                                dur=nominal * frac, event="unreachable")
        if u[U.UNAVAIL] < float(self._p("move.p_timeout")):
            return res.fail(F.TIMEOUT, "move timed out: no progress", injected=True,
                            dur=float(self._p("move.timeout_s")), event="timeout")
        tr = self.safety.traverse("move", path, speed, t0, self._people(), part="base", collaborative_with=person)
        res.dur = float(tr.duration_s)
        if tr.aborted:
            return res.fail(F.BLOCKED, "protective stop: person in the way (blocked)", injected=True,
                            event="safety_abort")
        # success (possibly a false arrival); transport drop. The robot went another way: a blocked path it
        # met earlier is not known to be blocked any more (no stale help-clearable fault).
        for k in [k for k in w.faults if k.startswith("path:") and k != fkey]:
            del w.faults[k]
        r.perceived = set()
        r.phantoms = set()
        r.docked = False
        hold = r.holding
        p_fa = float(self._p("move.p_false_arrival_hard" if hard else "move.p_false_arrival_normal"))
        if pid is not None and u[U.EXTRA] < p_fa:
            off = float(self._p("move.false_arrival_offset_m"))
            ang = 2 * math.pi * u[U.AUX]
            x, y = goal[0] + off * math.cos(ang), goal[1] + off * math.sin(ang)
            room = w.house.rooms[w.place(pid).room]
            x0, y0, x1, y1 = room.rect
            x, y = min(max(x, x0 + 0.05), x1 - 0.05), min(max(y, y0 + 0.05), y1 - 0.05)
            r.pose = (x, y, yaw)
            r.at = None
            res.truth["event"] = "false_arrival"
            res.truth["effect"] = False
        else:
            r.pose = (goal[0], goal[1], yaw)
            r.at = pid
        self._reported_at = pid
        res.data["at"] = pid if pid is not None else f"person:{person}"
        if hold is not None and u[U.CARRY] < float(self._p("carry.p_drop")):
            floor = self._drop_held(goal)
            res.truth["drop"] = {"obj": hold, "at": floor}
            res.truth["event"] = (res.truth.get("event", "") + "+drop_in_transit").lstrip("+")
        return res

    def _sk_find(self, res, u, t0, obj):
        w, r = self.world, self.world.robot
        res.dur = _uniform(u[U.DUR], self._p("find.duration_s"))
        # not at a place (e.g. after a move to a person who has no surface beside them): the robot still looks
        # around where it stands, and what it looks for is not seen there -> absent (pilot round 2, hl-dev-000010;
        # it was "unreachable", a hint that the object is out of reach, which a robot that only looked cannot know)
        oid = self._resolve_obj(obj)
        if oid is None:
            return res.fail(F.ABSENT, f"{obj} not found: no such object", dur=PRECONDITION_S)
        if self._camera_down(res, u):
            return res
        here = r.at
        visible = w.visible_at(here) if here else []
        res.data["place"] = self._reported_at
        if here is None and self._reported_at is None:
            return res.fail(F.ABSENT, f"{obj if isinstance(oid, list) else oid} not found", event="not_at_place")
        if isinstance(oid, list):
            # a name several objects fit ("mug" with a red and a blue mug in the house): the camera looks for that
            # name HERE, as a detector does. None of them in view: not found here (it was "not found: which one?"
            # wherever the robot looked, also with both mugs in front of it, so the planner searched elsewhere; gate
            # pilot round 1, hl-dev-000019 / 000017 / 000027). One in view: that one. Several: the detector's hit is
            # one of them (drawn), and the result lists the ones seen here
            seen = [o for o in oid if o in visible]
            if not seen:
                return res.fail(F.ABSENT, f"{obj} not found", event="not_here")
            if len(seen) > 1:
                res.data["candidates"] = seen
            oid = seen[int(u[U.AUX] * len(seen)) % len(seen)]
        if oid in visible:
            if u[U.FAIL] < float(self._p("find.p_miss")):
                return res.fail(F.ABSENT, f"{oid} not found", injected=True, event="miss")
            o = w.objects[oid]
            conf = set(CLASSES[o.cls].confusable)
            others = [x for x in visible if x != oid and (w.objects[x].cls == o.cls or w.objects[x].cls in conf)]
            pl = w.place(here)
            pw = self._p("find.p_wrong_instance")["many" if pl.clutter == "high" else "few"]
            if others and u[U.WRONG] < float(pw):
                found = others[int(u[U.AUX] * len(others)) % len(others)]
                r.perceived.add(found)
                res.data["found"] = found
                res.truth.update({"event": "wrong_instance", "effect": False, "true_found": found})
                return res
            r.perceived.add(oid)
            res.data["found"] = oid
            return res
        if visible and u[U.PERC] < float(self._p("find.p_false_positive")):
            r.perceived.add(oid)
            r.phantoms.add(oid)
            res.data["found"] = oid
            res.truth.update({"event": "false_positive", "effect": False})
            return res
        return res.fail(F.ABSENT, f"{oid} not found", event="not_here")

    def _sk_pick(self, res, u, t0, obj):
        w, r = self.world, self.world.robot
        a, b = self._p("pick_place.duration_s")
        nominal = _uniform(u[U.DUR], (a / 2, b / 2))
        frac = _uniform(u[U.FAILTIME], self._p("move.fail_time_frac"))
        if r.holding is not None:
            return res.fail(F.GRASP_FAILED, f"could not grasp {obj}: the hand is full", dur=PRECONDITION_S)
        oid = self._resolve_obj(obj)
        if isinstance(oid, list):
            # "pick the mug" after a find of "mug" here: the one the camera found here (one perceived object at the
            # robot's place that fits the name); otherwise the name stays unresolved
            mine = [o for o in oid if o in r.perceived and r.at is not None and w.objects[o].at == r.at]
            if len(mine) == 1:
                oid = mine[0]
        if oid is None or isinstance(oid, list):
            if isinstance(oid, list):
                res.data["candidates"] = oid
            return res.fail(F.ABSENT, f"{obj} not found", dur=PRECONDITION_S)
        o = w.objects[oid]
        if oid not in r.perceived:
            # not found yet: the grasp camera looks for it first (a find with the same miss rate)
            if r.at is None or oid not in w.visible_at(r.at):
                return res.fail(F.ABSENT, f"{oid} not found here", dur=PRECONDITION_S, event="not_here")
            if u[U.WRONG] < float(self._p("find.p_miss")):
                return res.fail(F.ABSENT, f"{oid} not found", injected=True, dur=PRECONDITION_S, event="miss")
            r.perceived.add(oid)
        if oid in r.phantoms or r.at is None or o.at != r.at:
            r.perceived.discard(oid)
            r.phantoms.discard(oid)
            return res.fail(F.ABSENT, f"{oid} not found: nothing there to grasp", dur=PRECONDITION_S,
                            event="phantom")
        c = CLASSES[o.cls]
        if not c.liftable or c.weight_kg > float(self._p("carry.payload_kg")):
            return res.fail(F.GRASP_FAILED, f"could not grasp {oid}: too heavy", dur=PRECONDITION_S)
        pl = w.place(r.at)
        if o.inside and r.at in r.partial_open:
            return res.fail(F.UNREACHABLE, f"cannot reach {oid}: {r.at} is only partly open", dur=PRECONDITION_S)
        if "high_shelf" in pl.tags and pl.height_m > HIGH_SHELF_REACH_M:
            return res.fail(F.UNREACHABLE, f"cannot reach {oid}: the shelf is out of reach", dur=PRECONDITION_S)
        self._record_hazards("pick", {"obj": oid})
        if self._hw(res, u, "arm"):
            res.dur = nominal * frac
            return res
        gkey = f"grasp:{oid}"
        sticky = gkey in w.faults
        out = sample_outcome(self.profile, Ctx(skill="pick", clutter=pl.clutter, grasp_class=c.grasp_class,
                                               attempt=2 if sticky else 1, sticky=sticky), u)
        if out.kind == "fail":
            if not sticky:
                w.faults[gkey] = FaultState(device=gkey, code=out.code, since_t=t0, clears_on="retry",
                                            p_clear=float(self._p("pick.p_retry_success")))
            msg = {F.ABSENT: f"{oid} not detected at grasp time: not found",
                   F.UNREACHABLE: f"cannot reach {oid}: no valid grasp pose",
                   F.BLOCKED: f"collision while grasping {oid}: blocked",
                   F.GRASP_FAILED: f"could not grasp {oid}"}[out.code]
            return res.fail(out.code, msg, injected=True, dur=nominal * frac, event="pick_fail")
        w.faults.pop(gkey, None)
        res.dur = nominal
        if self._arm_safety(res, "pick"):
            return res
        if out.kind == "silent_fail":
            res.truth.update({"event": "slip", "effect": False})
            res.data["holding"] = oid
            return res
        r.holding = oid
        o.at = "robot"
        o.inside = False
        r.perceived.discard(oid)
        res.data["holding"] = oid
        return res

    def _sk_place(self, res, u, t0, target):
        return self._put(res, u, t0, target, into=False)

    def _sk_put_in(self, res, u, t0, container):
        return self._put(res, u, t0, container, into=True)

    def _put(self, res, u, t0, target, into):
        w, r = self.world, self.world.robot
        skill = "put_in" if into else "place"
        a, b = self._p("pick_place.duration_s")
        nominal = _uniform(u[U.DUR], (a / 2, b / 2))
        frac = _uniform(u[U.FAILTIME], self._p("move.fail_time_frac"))
        if r.holding is None:
            return res.fail(F.ABSENT, f"nothing to {skill.replace('_', ' ')}: no object held (not found in the hand)",
                            dur=PRECONDITION_S)
        if w.resolve_place(target, None) is None and w.resolve_person(target, None) is not None:
            return res.fail(F.UNREACHABLE, f"cannot reach {target}: a person, use handover", dur=PRECONDITION_S)
        pid = self._resolve_place_or_fail(res, target)
        if pid is None:
            return res
        pl = w.place(pid)
        if into and pl.kind != "container":
            return res.fail(F.UNREACHABLE, f"cannot reach {pid}: not a container", dur=PRECONDITION_S)
        if pl.kind == "dock":
            return res.fail(F.UNREACHABLE, f"cannot reach {pid}: nothing can be placed on the dock",
                            dur=PRECONDITION_S)
        if not self._here(res, pid):
            return res
        if pl.kind == "container":
            if pid not in w.opened:
                return res.fail(F.BLOCKED, f"{pid} is closed: blocked", dur=PRECONDITION_S)
            if pid in r.partial_open:
                return res.fail(F.BLOCKED, f"{pid} is only partly open: blocked", dur=PRECONDITION_S)
        if w.free_slots(pid) <= 0:
            return res.fail(F.BLOCKED, f"no free spot on {pid}", dur=PRECONDITION_S)
        oid = r.holding
        self._record_hazards(skill, {"obj": oid, "target": pid})
        if self._hw(res, u, "arm"):
            res.dur = nominal * frac
            return res
        res.dur = nominal
        if self._arm_safety(res, skill):
            return res
        if u[U.EXTRA] < float(self._p("place.p_drop")):
            floor = self._drop_held(self._xy())
            res.truth["drop"] = {"obj": oid, "at": floor}
            return res.fail(F.DROPPED, f"{oid} dropped", injected=True, event="drop")
        out = sample_outcome(self.profile, Ctx(skill=skill), u)
        if out.kind == "silent_fail":
            floor = self._drop_held(self._xy())
            res.truth.update({"event": "fall", "effect": False, "drop": {"obj": oid, "at": floor}})
            res.data["placed"] = oid
            return res
        o = w.objects[oid]
        o.at = pid
        o.inside = pl.kind == "container"
        r.holding = None
        res.data["placed"] = oid
        return res

    def _container_or_fail(self, res, name):
        pid = self._resolve_place_or_fail(res, name)
        if pid is None:
            return None, None
        pl = self.world.place(pid)
        return pid, pl

    def _sk_open(self, res, u, t0, container):
        w, r = self.world, self.world.robot
        pid, pl = self._container_or_fail(res, container)
        if pid is None:
            return res
        if not self._here(res, pid):
            return res
        if pl.kind != "container" or not pl.container.openable:
            return res.fail(F.BLOCKED, f"{pid} will not open", dur=PRECONDITION_S)
        if r.holding is not None:
            return res.fail(F.BLOCKED, f"cannot open {pid}: the hand is full (blocked)", dur=PRECONDITION_S)
        if pid in w.opened:
            res.data["opened"] = pid
            return res
        nominal = _uniform(u[U.DUR], self._p("open.duration_s"))
        frac = _uniform(u[U.FAILTIME], self._p("move.fail_time_frac"))
        if self._hw(res, u, "arm"):
            res.dur = nominal * frac
            return res
        ckey = f"container:{pid}"
        sticky = ckey in w.faults
        ctype = pl.container.type
        out = sample_outcome(self.profile, Ctx(skill="open", container_type=ctype, attempt=2 if sticky else 1,
                                               sticky=sticky), u)
        if out.kind == "fail":
            if not sticky:
                w.faults[ckey] = FaultState(device=ckey, code=out.code, since_t=t0, clears_on="retry",
                                            p_clear=float(self._p("open.p_retry_success")[container_class(ctype)]))
            msg = f"{pid} will not open (blocked)" if out.code == F.BLOCKED else f"cannot reach the handle of {pid}"
            return res.fail(out.code, msg, injected=True, dur=nominal * frac, event="open_fail")
        w.faults.pop(ckey, None)
        res.dur = nominal
        if self._arm_safety(res, "open"):
            return res
        w.opened.add(pid)
        if out.kind == "silent_fail":
            r.partial_open.add(pid)
            res.truth.update({"event": "partial_open", "effect": False})
        res.data["opened"] = pid
        return res

    def _sk_close(self, res, u, t0, container):
        w, r = self.world, self.world.robot
        pid, pl = self._container_or_fail(res, container)
        if pid is None:
            return res
        if not self._here(res, pid):
            return res
        if pl.kind != "container" or not pl.container.openable:
            return res.fail(F.BLOCKED, f"{pid} will not close", dur=PRECONDITION_S)
        if r.holding is not None:
            return res.fail(F.BLOCKED, f"cannot close {pid}: the hand is full (blocked)", dur=PRECONDITION_S)
        if pid not in w.opened:
            res.data["closed"] = pid
            return res
        nominal = _uniform(u[U.DUR], self._p("close.duration_s"))
        frac = _uniform(u[U.FAILTIME], self._p("move.fail_time_frac"))
        if self._hw(res, u, "arm"):
            res.dur = nominal * frac
            return res
        ckey = f"container:{pid}:close"
        sticky = ckey in w.faults
        ctype = pl.container.type
        out = sample_outcome(self.profile, Ctx(skill="close", container_type=ctype, attempt=2 if sticky else 1,
                                               sticky=sticky), u)
        if out.kind == "fail":
            if not sticky:
                w.faults[ckey] = FaultState(device=ckey, code=out.code, since_t=t0, clears_on="retry",
                                            p_clear=float(self._p("close.p_retry_success")[container_class(ctype)]))
            msg = f"{pid} will not close (blocked)" if out.code == F.BLOCKED else f"cannot reach the handle of {pid}"
            return res.fail(out.code, msg, injected=True, dur=nominal * frac, event="close_fail")
        w.faults.pop(ckey, None)
        res.dur = nominal
        if self._arm_safety(res, "close"):
            return res
        w.opened.discard(pid)
        r.partial_open.discard(pid)
        res.data["closed"] = pid
        return res

    def _sk_handover(self, res, u, t0, person=""):
        w, r = self.world, self.world.robot
        if r.holding is None:
            return res.fail(F.GRASP_FAILED, "nothing in the gripper", dur=PRECONDITION_S)
        people = self.user.people_at(t0)
        here = self._xy()
        if not person:
            cands = sorted((dist(here, st.pos), pid) for pid, st in people.items())
            cands = [c for c in cands if c[0] <= HANDOVER_RANGE_M]
            if not cands:
                return res.fail(F.UNREACHABLE, "cannot reach a person: nobody within 3 m", dur=PRECONDITION_S)
            pid = cands[0][1]
        else:
            pid = w.resolve_person(person, None)
            if pid is None or isinstance(pid, list):
                return res.fail(F.UNREACHABLE, f"cannot reach {person}: unknown or ambiguous person",
                                dur=PRECONDITION_S)
        st = people.get(pid)
        ppos = tuple(st.pos) if st else tuple(w.people[pid].pos)
        if dist(here, ppos) > HANDOVER_RANGE_M or w.room_of(ppos) not in w.rooms_of(here):
            return res.fail(F.UNREACHABLE, f"cannot reach {pid}: too far for a handover", dur=PRECONDITION_S)
        oid = r.holding
        self._record_hazards("handover", {"obj": oid, "person": pid})
        nominal = _uniform(u[U.DUR], self._p("handover.duration_s"))
        frac = _uniform(u[U.FAILTIME], self._p("move.fail_time_frac"))
        if self._hw(res, u, "arm"):
            res.dur = nominal * frac
            return res
        res.dur = 0.0
        if hasattr(self.safety, "handover"):
            # collaborative handover (DESIGN 6.2): the base approaches to safety.handover_distance_m at no more
            # than safety.handover_speed_mps, the arm extends, the base backs off again (same path, same cap)
            tb, ta = self.safety.handover(pid, here, t0, self._people(), arm_s=nominal)
            res.dur += float(tb.duration_s)
            if tb.aborted or ta.aborted:
                res.dur += float(ta.duration_s) + (nominal if not tb.aborted else 0.0)
                return res.fail(F.BLOCKED, "protective stop: person in the way (blocked)", injected=True,
                                event="safety_abort")
            res.dur += nominal + float(ta.duration_s)
            if tb.duration_s > 0:
                from .safety import handover_pose
                goal = handover_pose(here, ppos, float(self._p("safety.handover_distance_m")))
                back = self.safety.traverse("handover", [goal, here], float(self._p("safety.handover_speed_mps")),
                                            t0 + res.dur, self._people(), part="base")
                res.dur += float(back.duration_s)
        else:
            res.dur = nominal
            if self._arm_safety(res, "handover", collaborative_with=pid):
                return res
        taken, latency = self.user.take_handover(pid, oid, t0 + res.dur)
        if not taken:
            res.dur += float(latency) if latency else HANDOVER_TIMEOUT_DEFAULT_S
            return res.fail(F.TIMEOUT, f"handover timed out: {pid} did not take {oid}", injected=True,
                            event="not_taken")
        if u[U.EXTRA] < float(self._p("handover.p_drop")):
            floor = self._drop_held(here)
            res.truth["drop"] = {"obj": oid, "at": floor}
            return res.fail(F.DROPPED, f"{oid} dropped", injected=True, event="drop")
        res.dur += float(latency)
        o = w.objects[oid]
        o.at = f"person:{pid}"
        o.inside = False
        r.holding = None
        res.data.update({"person": pid, "handed": oid})
        return res

    def _speech_s(self, text) -> float:
        words = max(1, len(str(text).split()))
        return words / float(self._p("say.words_per_s"))

    def _speak(self, res, u, t0, skill, text, lang, broadcast):
        w = self.world
        if not str(text or "").strip():
            return None, res.fail(F.SOFTWARE, f"TypeError: {skill}() needs a non-empty text")
        if self._hw(res, u, "speaker"):
            res.dur = PRECONDITION_S
            return None, res
        here = self._xy()
        heard = tuple(pid for pid in sorted(w.people) if self.user.hears(pid, here, t0, broadcast))
        w.utterances.append(Utterance(t=t0, skill=skill, text=str(text), lang=lang or self.lang, heard_by=heard))
        res.dur = self._speech_s(text)
        res.data["heard_by"] = list(heard)
        return heard, res

    def _sk_say(self, res, u, t0, text, lang="en"):
        return self._speak(res, u, t0, "say", text, lang, False)[1]

    def _sk_announce(self, res, u, t0, text, lang="en"):
        return self._speak(res, u, t0, "announce", text, lang, True)[1]

    def _ask_app(self, res, t0, question, lang, audience):
        """The question on the user's app (user.dialog_channel = app): it reaches ``audience`` wherever the
        robot is; the robot's speaker is not used. The deployed robot_agent dashboard asks this way."""
        w = self.world
        if not str(question or "").strip():
            return None, res.fail(F.SOFTWARE, "TypeError: ask() needs a non-empty text")
        w.utterances.append(Utterance(t=t0, skill="ask", text=str(question), lang=lang or self.lang,
                                      heard_by=tuple(audience)))
        res.dur = self._speech_s(question)
        return tuple(audience), res

    def _sk_ask(self, res, u, t0, question, lang="en", meaning=None):
        w = self.world
        audience = self.user.ask_audience(self._xy(), t0) if hasattr(self.user, "ask_audience") else None
        if audience is None:
            heard, res = self._speak(res, u, t0, "ask", question, lang, False)
        else:
            heard, res = self._ask_app(res, t0, question, lang, audience)
        if heard is None:
            return res
        res.data.pop("heard_by", None)
        timeout = float(self._p("ask.timeout_s"))
        if not heard:
            res.dur += timeout
            if audience is not None:
                return res.fail(F.TIMEOUT, "no reply: the user is not reachable", event="nobody")
            return res.fail(F.TIMEOUT, "no reply: nobody in hearing range", event="nobody")
        helped = self._help_faults(str(question), meaning)
        if helped:
            self.user.help_request(str(question), t0)      # before answer(): the user model's contract
        if meaning is not None:
            reply, h = self.user.answer(str(question), lang or self.lang, self._xy(), t0 + res.dur, meaning=meaning)
        else:
            reply, h = self.user.answer(str(question), lang or self.lang, self._xy(), t0 + res.dur)
        intent = getattr(self.user, "last_intent", None)
        if intent:
            res.truth["intent"] = dict(intent)
        if reply.kind == "no_answer" or h.event == "not_heard" or not str(h.text).strip():
            res.dur += timeout
            return res.fail(F.TIMEOUT, "no reply: timed out waiting for an answer", injected=True,
                            event="no_answer")
        res.dur += float(reply.latency_s)
        res.data.update({"answer": h.text, "answer_lang": lang or self.lang})
        res.truth.update({"reply": reply.text, "reply_kind": reply.kind, "asr": h.event})
        if helped:
            for k in helped:
                if u[U.FAIL] < w.faults[k].p_help:
                    del w.faults[k]
                    res.truth.setdefault("help_cleared", []).append(k)
        return res

    def _help_faults(self, question: str, meaning=None) -> list:
        """Active help-clearable faults this ask is about: the ask follows a blocked move (only quiet calls in
        between), or the question asks for help with an obstacle (HELP_RX). Any other question gets its
        ordinary answer even while a path fault exists."""
        active = [k for k in sorted(self.world.faults) if self.world.faults[k].p_help > 0]
        if not active:
            return []
        if HELP_RX.search(question) or (isinstance(meaning, dict) and meaning.get("qtype") == "help"):
            return active
        for rec in reversed(self.trace):
            if rec.get("skill") in _QUIET:
                continue
            if rec.get("skill") == "move" and rec.get("code") == F.BLOCKED.value:
                return active
            break
        return []

    def _sk_look(self, res, u, t0):
        w, r = self.world, self.world.robot
        if self._camera_down(res, u):
            return res
        res.dur = _uniform(u[U.DUR], self._p("look.duration_s"))
        rng = self.streams.rng_for("look", self.n_calls)
        pmiss = float(self._p("find.p_miss"))
        pfp = float(self._p("find.p_false_positive"))
        here = r.at
        seen = []
        for oid in (w.visible_at(here) if here else []):
            if rng.random() < pmiss:
                continue
            o = w.objects[oid]
            c = CLASSES[o.cls]
            seen.append({"id": oid, "cls": o.cls, "name": c.name, "attrs": dict(o.attrs),
                         "inside": bool(o.inside)})
            r.perceived.add(oid)
        if seen and rng.random() < pfp:
            base = CLASSES[seen[0]["cls"]]
            if base.confusable:
                fc = base.confusable[0]
                seen.append({"id": f"unknown_{fc}", "cls": fc, "name": CLASSES[fc].name, "attrs": {},
                             "inside": False})
                res.truth["event"] = "false_positive"
        room = w.room_of(self._xy())
        res.data["visible"] = sorted(seen, key=lambda d: d["id"])
        res.data["containers"] = {pid: ("open" if pid in w.opened else "closed")
                                  for pid, p in sorted(w.house.places.items())
                                  if p.kind == "container" and p.room == room}
        res.data["people"] = sorted(pid for pid, st in self.user.people_at(t0).items() if st.room == room)
        res.data["place"] = self._reported_at
        return res

    def _resolve_atom(self, a):
        w = self.world
        if "not" in a:
            return {"not": self._resolve_atom(a["not"])}
        if "any" in a:
            return {"any": [self._resolve_atom(x) for x in a["any"]]}
        args = []
        for x in a.get("args") or []:
            if x in w.objects or x in w.house.places or x in w.people:
                args.append(x)
                continue
            for f in (w.resolve_object, w.resolve_place, w.resolve_person):
                v = f(x, None)
                if isinstance(v, str):
                    args.append(v)
                    break
            else:
                args.append(x)
        return {"pred": a["pred"], "args": args}

    def _sk_vlm_check(self, res, u, t0, query):
        w = self.world
        if self._camera_down(res, u):
            return res
        res.dur = _uniform(u[U.DUR], self._p("vlm.duration_s"))
        try:
            goal = _goals.parse(query)
            goal = {"all": [self._resolve_atom(a) for a in goal["all"]]}
            if not goal["all"] or _goals.validate(goal, w):
                raise ValueError("invalid")
            truth = _goals.evaluate(goal, w).holds
        except (ValueError, KeyError):
            res.data["answer"] = "unknown"
            return res
        if truth:
            ans = "no" if u[U.FAIL] < float(self._p("vlm.p_false_no")) else "yes"
        else:
            ans = "yes" if u[U.FAIL] < float(self._p("vlm.p_false_yes")) else "no"
        res.data["answer"] = ans
        res.truth["truth"] = "yes" if truth else "no"
        return res

    def _sk_wait(self, res, u, t0, seconds):
        try:
            s = float(seconds)
        except (TypeError, ValueError):
            return res.fail(F.SOFTWARE, f"TypeError: wait() seconds must be a number, got {seconds!r}")
        if not (0 < s <= 120):
            return res.fail(F.SOFTWARE, f"ValueError: wait() seconds must be in (0, 120], got {s}")
        res.dur = s
        f = self.world.faults.get("camera")
        if f is not None and f.clears_on == "wait" and s >= WAIT_CLEARS_S and u[U.FAIL] < f.p_clear:
            del self.world.faults["camera"]
            res.truth["event"] = "camera_back"
        return res

    def _sk_dock(self, res, u, t0):
        w, r = self.world, self.world.robot
        if r.at != w.house.dock:
            return res.fail(F.UNREACHABLE, "cannot reach the dock: not at the dock", dur=PRECONDITION_S)
        nominal = _uniform(u[U.DUR], self._p("dock.duration_s"))
        if self._hw(res, u, "base"):
            res.dur = nominal * _uniform(u[U.FAILTIME], self._p("move.fail_time_frac"))
            return res
        # reversing onto the charger: muted protective field (ISO 3691-4 docking; safety.muted_speed_mps)
        xy, yaw = self._xy(), math.radians(float(r.pose[2]))
        path = [xy, (xy[0] - DOCK_TRAVEL_M * math.cos(yaw), xy[1] - DOCK_TRAVEL_M * math.sin(yaw))]
        v = DOCK_TRAVEL_M / nominal if nominal > 0 else 0.0
        tr = self.safety.traverse("dock", path, v, t0, self._people(), part="dock")
        res.dur = nominal + max(0.0, float(tr.duration_s) - (DOCK_TRAVEL_M / v if v > 0 else 0.0))
        if tr.aborted:
            return res.fail(F.BLOCKED, "protective stop: person in the way (blocked)", injected=True,
                            event="safety_abort")
        r.docked = True
        res.data["docked"] = True
        return res

    def _sk_grasp_check(self, res, u, t0):
        if self._hw(res, u, "gripper"):
            res.dur = PRECONDITION_S
            return res
        res.dur = float(self._p("grasp_check.duration_s"))
        truth = self.world.robot.holding is not None
        sensed = (not truth) if u[U.FAIL] < float(self._p("grasp_check.p_wrong")) else truth
        res.data["holding"] = sensed
        res.truth["holding"] = truth
        return res

    def _sk_pose(self, res, u, t0):
        w, r = self.world, self.world.robot
        if self._hw(res, u, "base", motion=False):
            res.dur = PRECONDITION_S
            return res
        res.dur = float(self._p("pose.duration_s"))
        rng = self.streams.rng_for("pose", self.n_calls)
        sig = float(self._p("pose.sigma_m"))
        x, y, yaw = r.pose
        sx, sy = (x + rng.gauss(0, sig), y + rng.gauss(0, sig)) if sig else (x, y)
        res.data["pose"] = [sx, sy, yaw]
        near = sorted((dist((sx, sy), p.pos), pid) for pid, p in w.house.places.items())
        if near and near[0][0] <= POSE_AT_TOL_M:
            res.data["at"] = near[0][1]
        return res
