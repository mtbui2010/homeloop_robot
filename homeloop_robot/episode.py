"""Episode factory: one house + profile + seed -> world, robot, user, safety monitor (docs/architecture.md).

The bench always builds episodes with :func:`make_episode`. When the simulated user
(``homeloop_robot.user``) or the safety monitor (``homeloop_robot.safety``) is not installed, the
Null fallbacks below are used: nobody answers questions, everyone stays at their seat, and motion is
never slowed or stopped (minimum separation is still measured from geometry).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Optional

from .clock import SimClock
from .rng import Streams
from .types import Heard, PersonState, Traverse, UserReply
from .world import World, dist, from_house, polyline_length, polyline_min_distance

# NullUser: a person takes a handed-over object after this many seconds (an engineering default of
# the fallback user, not a calibrated value; the simulated user replaces it).
NULL_HANDOVER_LATENCY_S = 3.0


class NullUser:
    """Fallback user model: hears instructions perfectly, never answers questions, takes handovers,
    never moves, never interrupts."""

    def __init__(self, world: World, *args, **kwargs):
        self.world = world

    def hear_instruction(self, text: str, lang: str) -> Heard:
        return Heard(text=text, event="ok")

    def answer(self, question: str, lang: str, robot_xy, t: float):
        return UserReply(text="", kind="no_answer", latency_s=0.0, heard_question=False), Heard("", "not_heard")

    def take_handover(self, person_id: str, obj_id: str, t: float):
        return True, NULL_HANDOVER_LATENCY_S

    def hears(self, person_id: str, robot_xy, t: float, broadcast: bool) -> bool:
        p = self.world.people.get(person_id)
        if p is None:
            return False
        pr = self.world.room_of(p.pos)
        rr = self.world.rooms_of(robot_xy)
        if pr in rr:
            return True
        return bool(broadcast and any(pr in self.world.adjacent_rooms(r) for r in rr))

    def events_between(self, t0: float, t1: float) -> list:
        return []

    def people_at(self, t: float) -> dict:
        return {pid: PersonState(id=pid, pos=tuple(p.pos), vel=(0.0, 0.0), room=self.world.room_of(p.pos))
                for pid, p in sorted(self.world.people.items())}

    def help_request(self, question: str, t: float) -> None:
        return None


class NullSafety:
    """Fallback safety monitor: no slow-down, no stop, no violations; separation measured only."""

    def __init__(self, world: World, *args, **kwargs):
        self.world = world
        self._min_sep: Optional[float] = None

    def traverse(self, skill, path, v_nominal, t0, people, *, part="base", collaborative_with=None) -> Traverse:
        path = [tuple(p[:2]) for p in path]
        if part == "base":
            dur = polyline_length(path) / v_nominal if v_nominal > 0 else 0.0
        else:
            dur = 0.0                            # arm: no extra time
        rooms = set()
        for p in path:
            rooms |= set(self.world.rooms_of(p))
        sep = None
        for pid, st in sorted(people(t0).items()):
            if pid == collaborative_with or st.room not in rooms:
                continue
            d = polyline_min_distance(st.pos, path) if len(path) > 1 else dist(st.pos, path[0])
            sep = d if sep is None else min(sep, d)
        if sep is not None:
            self._min_sep = sep if self._min_sep is None else min(self._min_sep, sep)
        return Traverse(duration_s=dur, slow_s=0.0, stopped_s=0.0, aborted=False, min_sep_m=sep, violations=())

    def stats(self) -> dict:
        return {"violations": 0, "severe": 0, "min_separation_m": self._min_sep, "time_in_slow_s": 0.0,
                "n_protective_stops": 0, "violation_list": [],
                "semantic": [e.to_json() for e in self.world.semantic_violations]}


@dataclass
class Episode:
    world: World
    robot: object
    user: object
    safety: object
    clock: SimClock
    streams: Streams
    profile: object
    lang: str
    key: str


def _optional(module: str, attr: str):
    """``homeloop_robot.<module>.<attr>`` or None when that module is not installed."""
    name = f"homeloop_robot.{module}"
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name == name:
            return None
        raise
    return getattr(mod, attr)


def make_episode(house: str, seed_state: int, profile, seed: int, *, lang: str = "en",
                 user_spec: Optional[dict] = None, key: str = "", user_impl: Optional[str] = None,
                 safety_impl: Optional[str] = None) -> Episode:
    """Build one episode. ``profile`` is a name or a :class:`Profile`. ``user_impl`` /
    ``safety_impl`` = "null" force the Null fallbacks (tests); default: the full models when installed."""
    from .profiles import Profile, load_profile
    from .skills import Robot

    prof = profile if isinstance(profile, Profile) else load_profile(str(profile))
    world = from_house(house, seed_state)
    streams = Streams(seed, key)
    clock = SimClock()
    SimUser = None if user_impl == "null" else _optional("user", "SimUser")
    SafetyMonitor = None if safety_impl == "null" else _optional("safety", "SafetyMonitor")
    user = SimUser(world, prof, streams, lang, user_spec) if SimUser else NullUser(world)
    safety = SafetyMonitor(world, prof, streams) if SafetyMonitor else NullSafety(world)
    robot = Robot(world, prof, streams, clock, user, safety, lang=lang)
    return Episode(world=world, robot=robot, user=user, safety=safety, clock=clock, streams=streams,
                   profile=prof, lang=lang, key=key)
