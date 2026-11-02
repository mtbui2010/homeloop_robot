"""SimUser: the simulated household user (DESIGN 5, docs/user_model.md).

* dialog: answers to the robot's questions (content from ``dialog.py``), with the correct / not-sure / wrong
  mix and answer latency of Zou et al. 2020 (arXiv:2008.00279, Table 1, Sec. 3.3), a patience limit
  (same source, Fig. 2), silence (assumed), and ASR noise on what the robot hears (``asr.py``);
* hearing: same room or within ``user.hearing_range_m``; announcements also reach adjacent rooms;
* motion: Poisson walks between seats at the person's gait speed (Bohannon & Andrews 2011 decade table;
  Studenski et al. 2011 for older adults), times an indoor factor (assumed);
* handover: take latency and an unresponsive probability (assumed);
* interruptions: the task's scripted interrupt, or a random stop with ``user.p_interrupt_stop`` (assumed).

Everything is a pure function of the episode streams; nothing reads the wall clock.
"""
from __future__ import annotations

import math
from typing import Any

from homeloop_robot import asr as _asr
from homeloop_robot import dialog
from homeloop_robot._hs_compat import (
    Heard,
    PersonState,
    UserEvent,
    UserReply,
    age_lower,
    dist,
    param,
    point_along,
    polyline_length,
    r6,
    adjacent_rooms,
    room_of,
    rooms_at,
    world_path,
)

PARAMS = (
    "user.answer.p_wrong",
    "user.answer.p_not_sure",
    "user.latency",
    "user.patience_questions",
    "user.p_no_answer",
    "user.p_interrupt_stop",
    "user.interrupt_after_calls",
    "user.gait_mps_men",
    "user.gait_mps_women",
    "user.gait_older",
    "user.gait_child_mps",
    "user.indoor_gait_factor",
    "user.motion.rate_per_h",
    "user.motion.pause_s",
    "user.hearing_range_m",
    "user.p_location_unknown",
    "user.handover_latency",
    "user.handover_timeout_s",
    "user.p_unresponsive",
    "user.approach_distance_m",
    "user.asr_on_instruction",
    "user.dialog_channel",
)

HORIZON_S = 3600.0  # people stop scheduling new walks after this (episodes are much shorter)
SEAT_BODY_OFFSET_M = 0.5  # body position of a seat = approach pose + 0.5 m along the approach yaw (geometry)


def lognormal(rng, median: float, sigma: float, lo: float) -> float:
    return max(lo, math.exp(math.log(median) + sigma * rng.gauss(0.0, 1.0)))


def decade_key(lo: int, keys) -> str | None:
    for k in sorted(keys):
        a, b = k.split("-")
        if int(a) <= lo <= int(b):
            return k
    return None


class SimUser:
    """Implements the ``UserModel`` protocol (DESIGN 5.1)."""

    def __init__(self, world: Any, profile: Any, streams: Any, lang: str = "en", spec: dict | None = None):
        if lang not in ("en", "ko"):
            raise ValueError(f"lang must be en or ko, not {lang!r}")
        self.world = world
        self.profile = profile
        self.streams = streams
        self.lang = lang
        self.spec = spec
        g = lambda n: param(profile, n)  # noqa: E731
        self.p_wrong = float(g("user.answer.p_wrong"))
        self.p_not_sure = float(g("user.answer.p_not_sure"))
        self.latency = dict(g("user.latency"))
        self.patience = int(g("user.patience_questions"))
        self.p_no_answer = float(g("user.p_no_answer"))
        self.p_interrupt_stop = float(g("user.p_interrupt_stop"))
        self.interrupt_after = list(g("user.interrupt_after_calls"))
        self.rate_per_h = float(g("user.motion.rate_per_h"))
        self.pause_s = list(g("user.motion.pause_s"))
        self.hearing_range_m = float(g("user.hearing_range_m"))
        self.p_location_unknown = float(g("user.p_location_unknown"))
        self.handover_latency = dict(g("user.handover_latency"))
        self.handover_timeout_s = float(g("user.handover_timeout_s"))
        self.p_unresponsive = float(g("user.p_unresponsive"))
        self.approach_distance_m = float(g("user.approach_distance_m"))
        self.asr_on_instruction = bool(g("user.asr_on_instruction"))
        # how the task and the robot's questions travel between the user and the robot (docs/user_model.md):
        # "app" = the user's phone / tablet app (the task is given there, the robot's ask reaches the user there
        # wherever the robot is, answers are spoken into it); "voice" = the robot's own speaker and microphone
        self.dialog_channel = str(g("user.dialog_channel"))
        if self.dialog_channel not in ("app", "voice"):
            raise ValueError(f"user.dialog_channel must be app or voice, not {self.dialog_channel!r}")
        # the goal atoms the user asked for ({"all": [...]}); set by the runner (set_wants), None = unknown
        self.wants: dict | None = None
        self.asr = _asr.ASRRates(profile)
        users = sorted(pid for pid, p in world.people.items() if getattr(p, "role", "") == "user")
        self.user_id = users[0] if users else (sorted(world.people)[0] if world.people else None)
        self.asleep = set((spec or {}).get("asleep", []) or [])
        self.n_asks = 0
        self.n_handovers = 0
        self._help: tuple[str, float] | None = None
        self.log: list[dict] = []
        self._speed = {pid: self._gait(pid) for pid in sorted(world.people)}
        self._sched = {pid: self._schedule(pid) for pid in sorted(world.people)}

    # ------------------------------------------------------------------ motion
    def _gait(self, pid: str) -> float:
        p = self.world.people[pid]
        g = lambda n: param(self.profile, n)  # noqa: E731
        factor = float(g("user.indoor_gait_factor"))
        lo = age_lower(getattr(p, "age_group", None))
        if getattr(p, "child", False):
            v = float(g("user.gait_child_mps"))
        elif lo is not None and lo >= 65:
            older = dict(g("user.gait_older"))
            rng = self.streams.rng_for("user", "gait", pid)
            v = min(older["max"], max(older["min"], rng.gauss(older["mean"], older["sd"])))
        else:
            sex = getattr(p, "sex", "")
            tables = []
            if sex in ("male", "female"):
                tables = [dict(g("user.gait_mps_men" if sex == "male" else "user.gait_mps_women"))]
            else:
                tables = [dict(g("user.gait_mps_men")), dict(g("user.gait_mps_women"))]
            vals = []
            for tab in tables:
                k = decade_key(lo if lo is not None else 30, tab) or "30-39"
                vals.append(float(tab[k]))
            v = sum(vals) / len(vals)
        return v * factor

    def _seat_pos(self, pid: str, place_id: str) -> tuple[float, float]:
        person = self.world.people[pid]
        if place_id == getattr(person, "seat", None):
            return tuple(map(float, person.pos))
        pl = self.world.house.places[place_id]
        body = getattr(pl, "person_pos", None)
        if body is not None:
            return tuple(map(float, body))
        yaw = math.radians(getattr(pl, "yaw_deg", 0.0))
        return (pl.pos[0] + SEAT_BODY_OFFSET_M * math.cos(yaw), pl.pos[1] + SEAT_BODY_OFFSET_M * math.sin(yaw))

    def destinations(self, pid: str) -> list[str]:
        person = self.world.people[pid]
        own = [person.seat] + list(getattr(person, "alt_seats", []) or []) + list(getattr(person, "walks_to", []) or [])
        seats = [k for k, pl in self.world.house.places.items() if getattr(pl, "kind", "") == "seat"]
        return sorted({d for d in own + seats if d in self.world.house.places})

    def _schedule(self, pid: str) -> list[tuple]:
        """Walks: (t_start, t_end, path, place). Departures: Exp(rate) gaps, at least a pause U(pause_s)."""
        if self.rate_per_h <= 0:
            return []
        rng = self.streams.rng_for("user", "motion", pid)
        dests = self.destinations(pid)
        cur = self.world.people[pid].seat
        pos = tuple(map(float, self.world.people[pid].pos))
        speed = self._speed[pid]
        t = 0.0
        out = []
        while True:
            gap = rng.expovariate(self.rate_per_h / 3600.0)
            pause = rng.uniform(self.pause_s[0], self.pause_s[1])
            depart = t + max(gap, pause)
            if depart >= HORIZON_S:
                break
            choices = [d for d in dests if d != cur]
            if not choices or speed <= 0:
                break
            dest = choices[rng.randrange(len(choices))]
            dpos = self._seat_pos(pid, dest)
            path = world_path(self.world, pos, dpos)
            dur = polyline_length(path) / speed
            out.append((depart, depart + dur, path, dest))
            t, pos, cur = depart + dur, dpos, dest
        return out

    def _state(self, pid: str, t: float) -> PersonState:
        person = self.world.people[pid]
        pos = tuple(map(float, person.pos))
        vel = (0.0, 0.0)
        for (t0, t1, path, _dest) in self._sched[pid]:
            if t < t0:
                break
            if t < t1:
                speed = self._speed[pid]
                s = (t - t0) * speed
                pos = point_along(path, s)
                ahead = point_along(path, s + 1e-3)
                dx, dy = ahead[0] - pos[0], ahead[1] - pos[1]
                n = math.hypot(dx, dy)
                vel = (speed * dx / n, speed * dy / n) if n > 0 else (0.0, 0.0)
                break
            pos = tuple(map(float, path[-1]))
        room = room_of(self.world, pos)
        return PersonState(pid, (r6(pos[0]), r6(pos[1])), (r6(vel[0]), r6(vel[1])), room,
                           pid not in self.asleep)

    def place_of(self, pid: str, t: float) -> tuple:
        """(place id, moving): the seat a person is at, or the one they are walking to."""
        place = self.world.people[pid].seat
        for (t0, t1, _path, dest) in self._sched[pid]:
            if t < t0:
                break
            if t < t1:
                return dest, True
            place = dest
        return place, False

    def people_at(self, t: float) -> dict:
        return {pid: self._state(pid, t) for pid in sorted(self.world.people)}

    def walks(self, pid: str) -> list[dict]:
        return [{"t0": r6(a), "t1": r6(b), "to": d} for (a, b, _p, d) in self._sched[pid]]

    # ------------------------------------------------------------------ hearing
    def hears(self, person_id: str, robot_xy, t: float, broadcast: bool = False) -> bool:
        st = self._state(person_id, t)
        if not st.awake:
            return False
        rrooms = rooms_at(self.world, robot_xy)
        if st.room is not None and st.room in rrooms:
            return True
        if broadcast and any(st.room in adjacent_rooms(self.world, r) for r in rrooms):
            return True
        return dist(robot_xy, st.pos) <= self.hearing_range_m

    def reachable(self, robot_xy, t: float) -> bool:
        """Does a question of the robot reach the user (the person who gave the task)? app: whenever the user is
        awake (their phone is with them); voice: within hearing range of the robot."""
        uid = self.user_id
        if uid is None:
            return False
        if self.dialog_channel == "app":
            return self._state(uid, t).awake
        return self.hears(uid, robot_xy, t, False)

    def ask_audience(self, robot_xy, t: float):
        """Who a question of the robot reaches: None = the robot's own speaker (everyone in hearing range);
        else the people the app channel reaches (the user, or nobody)."""
        if self.dialog_channel != "app":
            return None
        return (self.user_id,) if self.reachable(robot_xy, t) else ()

    def set_wants(self, goal: dict | None) -> None:
        """What the user asked for (goal atoms), so they can answer questions about their own request."""
        self.wants = {"all": list((goal or {}).get("all") or [])} if goal else None

    # ------------------------------------------------------------------ dialog
    def hear_instruction(self, text: str, lang: str) -> Heard:
        """What the robot hears of the task instruction: app = near-field (the user's phone / tablet); voice =
        spoken at the robot from the approach distance."""
        if not self.asr_on_instruction:
            return Heard(text, "ok")
        cond = "app" if self.dialog_channel == "app" else self.asr.condition(self.approach_distance_m)
        return _asr.corrupt(text, lang, cond, self.streams.rng_for("user", "instruction"), self.asr)

    def help_request(self, question: str, t: float) -> None:
        """The robot asked while a help-clearable fault is active (call before ``answer``)."""
        self._help = (question, t)

    def _no_answer(self, question: str, t: float, heard_q: bool, why: str):
        reply = UserReply("", "no_answer", 0.0, heard_q)
        self.log.append({"t": r6(t), "q": question, "kind": "no_answer", "why": why, "text": "", "heard": ""})
        return reply, Heard("", "not_heard")

    def answer(self, question: str, lang: str, robot_xy, t: float):
        self.n_asks += 1
        k = self.n_asks
        rng = self.streams.rng_for("user", "answer", k)
        uid = self.user_id
        help_pending = self._help is not None and self._help[0] == question
        self._help = None
        if uid is None:
            return self._no_answer(question, t, False, "nobody")
        if not self.reachable(robot_xy, t):
            return self._no_answer(question, t, False, "out_of_range" if self.dialog_channel == "voice"
                                   else "unreachable")
        if k > self.patience:
            return self._no_answer(question, t, True, "patience")
        if rng.random() < self.p_no_answer:
            return self._no_answer(question, t, True, "silent")
        L = self.lang
        if help_pending:
            kind, text, rule = "yes", dialog.TEXT["help_ok"][L], "help"
        else:
            knows = rng.random() >= self.p_location_unknown
            places = sorted(pid for pid, pl in self.world.house.places.items()
                            if getattr(pl, "kind", "") in ("surface", "container"))
            other = places[rng.randrange(len(places))] if places else None
            gv = None
            if self.wants:
                gv = dialog.GoalView(self.world, self.wants, uid, lambda pid: self.place_of(pid, t)[0])
            c = dialog.compose(question, L, self.spec, self.world, knows_location=knows, other_place=other,
                               user_place=self.place_of(uid, t), goal=gv)
            kind, text, rule = c.kind, c.text, c.rule
            if c.informative:
                u = rng.random()
                if u < self.p_wrong:
                    if c.wrong_text is not None:
                        kind, text = "wrong", c.wrong_text
                    else:  # no alternative answer exists: the user is unsure instead
                        kind, text = "not_sure", dialog.TEXT["not_sure"][L]
                elif u < self.p_wrong + self.p_not_sure:
                    kind, text = "not_sure", dialog.TEXT["not_sure"][L]
        lat = self.latency
        latency = lognormal(rng, lat["median"], lat["sigma"], lat["min"])
        st = self._state(uid, t)
        # app: spoken into the user's own device, the near condition of the instruction; voice: robot-user distance
        cond = "app" if self.dialog_channel == "app" else self.asr.condition(dist(robot_xy, st.pos))
        heard = _asr.corrupt(text, L, cond, self.streams.rng_for("user", "asr", k), self.asr)
        self.log.append({"t": r6(t), "q": question, "kind": kind, "why": rule, "text": text, "heard": heard.text,
                         "asr": heard.event, "cond": cond, "latency_s": r6(latency)})
        return UserReply(text, kind, r6(latency), True), heard

    # ------------------------------------------------------------------ handover
    def take_handover(self, person_id: str, obj_id: str, t: float) -> tuple[bool, float]:
        """(taken, latency_s). Not taken -> latency = the handover timeout (time the robot waited)."""
        self.n_handovers += 1
        rng = self.streams.rng_for("user", "handover", self.n_handovers)
        if person_id not in self.world.people or not self._state(person_id, t).awake:
            return False, r6(self.handover_timeout_s)
        if rng.random() < self.p_unresponsive:
            return False, r6(self.handover_timeout_s)
        hl = self.handover_latency
        lat = lognormal(rng, hl["median"], hl["sigma"], hl["min"])
        if lat > self.handover_timeout_s:
            return False, r6(self.handover_timeout_s)
        return True, r6(lat)

    # ------------------------------------------------------------------ interruptions
    def events_between(self, t0: float, t1: float) -> list:
        """Time-scheduled user events. Interruptions are call-indexed (``interrupt_plan``), so none here."""
        return []

    def interrupt_plan(self) -> dict | None:
        """The interruption the runner triggers at the start of motion call ``after_calls + 1`` (DESIGN 5.5):
        the task's scripted ``spec.interrupt``, else a random stop with ``user.p_interrupt_stop``."""
        spec_i = (self.spec or {}).get("interrupt")
        if spec_i:
            return dict(spec_i)
        rng = self.streams.rng_for("user", "interrupt")
        if rng.random() < self.p_interrupt_stop:
            lo, hi = int(self.interrupt_after[0]), int(self.interrupt_after[1])
            return {"after_calls": rng.randint(lo, hi), "kind": "stop", "text": dict(dialog.TEXT["stop"]),
                    "new_goal": None, "random": True}
        return None

    def interrupt_event(self, t: float) -> UserEvent | None:
        plan = self.interrupt_plan()
        if plan is None:
            return None
        return UserEvent(r6(t), plan["kind"], plan["text"][self.lang], plan.get("new_goal"))

    def stats(self) -> dict:
        kinds: dict[str, int] = {}
        for e in self.log:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        return {"asks": self.n_asks, "handovers": self.n_handovers, "answers": dict(sorted(kinds.items()))}


def consistency(world: Any, profile: Any, n: int = 20000, seed: int = 0, lang: str = "en") -> list[dict]:
    """Empirical answer-kind rates of SimUser vs the profile (DESIGN 13.3), on a clarification question
    between two objects of ``world`` asked from next to the user. One row per parameter."""
    from homeloop_robot._hs_compat import Streams, binomial_row

    oids = sorted(world.objects)[:2]
    if len(oids) < 2:
        raise ValueError("consistency needs a world with two objects")
    names = {o: {lg: dialog.object_names(world, o, lg)[0] for lg in ("en", "ko")} for o in oids}
    spec = {"intended": oids[1],
            "candidates": [{"id": o, "mentions": {lg: [names[o][lg]] for lg in ("en", "ko")}} for o in oids],
            "answer": {lg: dialog.TEXT["candidate"][lg].format(mention=names[oids[1]][lg]) for lg in ("en", "ko")}}
    q = {"en": f"Which one, the {names[oids[0]]['en']} or the {names[oids[1]]['en']}?",
         "ko": f"{names[oids[0]]['ko']}이요, {names[oids[1]]['ko']}이요? 어느 거요?"}[lang]
    u = SimUser(world, profile, Streams(seed, "user-consistency"), lang, spec)
    u.patience = n + 1
    if u.user_id is None:
        raise ValueError("consistency needs a world with a user")
    xy = tuple(world.people[u.user_id].pos)
    kinds: dict[str, int] = {}
    for _ in range(n):
        r, _h = u.answer(q, lang, xy, 0.0)
        kinds[r.kind] = kinds.get(r.kind, 0) + 1
        u.log.clear()
    answered = n - kinds.get("no_answer", 0)
    return [
        binomial_row("user.p_no_answer", u.p_no_answer, kinds.get("no_answer", 0), n, "per question in range"),
        binomial_row("user.answer.p_wrong", u.p_wrong, kinds.get("wrong", 0), answered, "per answered question"),
        binomial_row("user.answer.p_not_sure", u.p_not_sure, kinds.get("not_sure", 0), answered,
                     "per answered question"),
    ]
