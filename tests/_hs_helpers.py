"""Test helpers for the user / ASR / dialog / safety / hazard modules.

``load_params(name)`` resolves the user and safety fragments of a profile from the YAML files (real) or by
the documented derive rules (ideal: zero every user_noise / safety_noise value, people static). A small fake
world mirrors the attribute names of ``homeloop_robot.world`` (DESIGN 2.1) so these tests run without the
robot core.
"""
from __future__ import annotations

import copy
import functools
import math
import pathlib
from dataclasses import dataclass, field

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "homeloop_robot"
FRAGMENTS = [PKG / "profiles" / "real" / "user.yaml", PKG / "profiles" / "real" / "safety.yaml"]
NOISE_ROLES = ("failure", "user_noise", "safety_noise")


@functools.lru_cache(maxsize=None)
def _entries() -> dict:
    out: dict = {}
    for f in FRAGMENTS:
        if not f.exists():
            continue
        doc = yaml.safe_load(f.read_text())
        for k, v in doc["params"].items():
            assert k not in out, f"duplicate {k}"
            out[k] = v
    return out


def load_entries() -> dict:
    return copy.deepcopy(_entries())


def _zero(e: dict):
    """The core's zero rule (profiles.zero_value): prob, prob_map and rate_per_h go to 0; other kinds keep."""
    if e["kind"] in ("prob", "rate_per_h"):
        return 0.0
    if e["kind"] == "prob_map":
        return {k: 0.0 for k in e["value"]}
    return copy.deepcopy(e["value"])


def load_params(name: str = "real", **overrides) -> dict:
    entries = load_entries()
    vals = {k: copy.deepcopy(e["value"]) for k, e in entries.items()}
    if name == "ideal":
        for k, e in entries.items():
            if e["role"] in NOISE_ROLES:
                vals[k] = _zero(e)
        vals["user.motion.rate_per_h"] = 0.0
    elif name != "real":
        raise ValueError(name)
    vals.update(overrides)
    return vals


class Streams:
    def __init__(self, seed: int = 0, key: str = "test"):
        from homeloop_robot._hs_compat import Streams as S
        self._s = S(seed, key)

    def rng_for(self, *parts):
        return self._s.rng_for(*parts)

    def stream(self, name):
        return self._s.stream(name)


# ----------------------------------------------------------------------------------------- fake world
@dataclass
class Room:
    id: str
    name: dict
    rect: tuple


@dataclass
class Door:
    rooms: tuple
    at: tuple
    width_m: float = 0.9


@dataclass
class Container:
    type: str
    openable: bool = True
    opened: bool = False


@dataclass
class Place:
    id: str
    room: str
    kind: str
    name: dict
    pos: tuple
    yaw_deg: float = 0.0
    tags: list = field(default_factory=list)
    container: Container | None = None
    aliases: dict = field(default_factory=dict)


@dataclass
class Obj:
    id: str
    cls: str
    name: dict
    at: str
    tags: tuple = ()
    attrs: dict = field(default_factory=dict)
    inside: bool = False


@dataclass
class Person:
    id: str
    role: str
    name: dict
    age_group: str
    sex: str
    child: bool
    seat: str
    pos: tuple
    alt_seats: list = field(default_factory=list)


@dataclass
class RobotState:
    at: str | None = "dock@living"
    pose: tuple = (4.5, 0.8, 0.0)
    holding: str | None = None


@dataclass
class House:
    rooms: dict
    doors: list
    places: dict


class FakeWorld:
    """Two rooms: living [0,6]x[0,5], kitchen [6,10]x[0,5], one door at (6, 2.5)."""

    def __init__(self, people=None):
        rooms = {"living": Room("living", {"en": "living room", "ko": "거실"}, (0, 0, 6, 5)),
                 "kitchen": Room("kitchen", {"en": "kitchen", "ko": "부엌"}, (6, 0, 10, 5)),
                 "bedroom": Room("bedroom", {"en": "bedroom", "ko": "침실"}, (0, 5, 6, 9))}
        doors = [Door(("living", "kitchen"), (6.0, 2.5)), Door(("living", "bedroom"), (4.5, 5.0))]
        P = Place
        places = {
            "armchair@living": P("armchair@living", "living", "seat", {"en": "armchair", "ko": "안락의자"}, (1.6, 3.4), 135),
            "sofa@living": P("sofa@living", "living", "seat", {"en": "sofa", "ko": "소파"}, (3.0, 4.0), 90),
            "table@living": P("table@living", "living", "surface", {"en": "coffee table", "ko": "탁자"}, (3.5, 1.5), 180,
                              ["child_reachable"]),
            "dock@living": P("dock@living", "living", "dock", {"en": "dock", "ko": "충전대"}, (4.5, 0.8), 0),
            "floor@living": P("floor@living", "living", "floor", {"en": "floor", "ko": "바닥"}, (2.5, 2.0), 0,
                              ["carpet"]),
            "floor@hall": P("floor@hall", "living", "floor", {"en": "hall floor", "ko": "현관 바닥"}, (5.5, 4.5), 0,
                            ["exit_path"]),
            "counter@kitchen": P("counter@kitchen", "kitchen", "surface", {"en": "counter", "ko": "조리대"}, (8.5, 1.0),
                                 -90, ["food_prep"]),
            "stove@kitchen": P("stove@kitchen", "kitchen", "surface", {"en": "stove", "ko": "가스레인지"}, (7.0, 1.0), -90,
                               ["heat_source"]),
            "fridge@kitchen": P("fridge@kitchen", "kitchen", "container", {"en": "fridge", "ko": "냉장고"}, (9.0, 3.5),
                                0, ["food_storage"], Container("fridge")),
            "microwave@kitchen": P("microwave@kitchen", "kitchen", "container", {"en": "microwave", "ko": "전자레인지"},
                                   (7.5, 3.8), 90, ["electrical"], Container("appliance")),
            "sink@kitchen": P("sink@kitchen", "kitchen", "surface", {"en": "sink", "ko": "싱크대"}, (9.5, 1.5), 0, ["wet"]),
            "bed@bedroom": P("bed@bedroom", "bedroom", "seat", {"en": "bed", "ko": "침대"}, (2.0, 7.0), 90),
            "shelf@bedroom": P("shelf@bedroom", "bedroom", "surface", {"en": "shelf", "ko": "선반"}, (5.0, 8.0), 0,
                               ["high_shelf", "child_reachable"]),
        }
        self.house = House(rooms, doors, places)
        O = Obj
        self.objects = {
            "mug_1": O("mug_1", "mug", {"en": "red mug", "ko": "빨간 머그컵"}, "table@living", ("fragile",), {"color": "red"}),
            "mug_2": O("mug_2", "mug", {"en": "blue mug", "ko": "파란 머그컵"}, "counter@kitchen", ("fragile",),
                       {"color": "blue"}),
            "knife_1": O("knife_1", "knife", {"en": "knife", "ko": "칼"}, "counter@kitchen", ("sharp", "metal")),
            "bleach_1": O("bleach_1", "bleach", {"en": "bleach", "ko": "락스"}, "sink@kitchen", ("toxic", "liquid")),
            "water_1": O("water_1", "water_bottle", {"en": "water bottle", "ko": "물병"}, "counter@kitchen", ("liquid",)),
            "phone_1": O("phone_1", "phone", {"en": "phone", "ko": "휴대폰"}, "table@living", ("electronic",)),
            "lighter_1": O("lighter_1", "lighter", {"en": "lighter", "ko": "라이터"}, "table@living", ("flammable",)),
            "pills_1": O("pills_1", "pills", {"en": "pills", "ko": "약"}, "fridge@kitchen", ("medicine",), inside=True),
            "tea_1": O("tea_1", "tea", {"en": "hot tea", "ko": "뜨거운 차"}, "counter@kitchen", ("hot", "liquid")),
            "fork_1": O("fork_1", "fork", {"en": "fork", "ko": "포크"}, "counter@kitchen", ("metal",)),
        }
        if people is None:
            people = {
                "grandma": Person("grandma", "user", {"en": "grandma", "ko": "할머니"}, "80-99", "female", False,
                                  "armchair@living", (1.0, 4.2), ["bed@bedroom"]),
                "child": Person("child", "other", {"en": "child", "ko": "아이"}, "5-9", "male", True, "bed@bedroom",
                                (2.0, 7.8), []),
            }
        self.people = people
        self.robot = RobotState()
        self.semantic_violations: list = []

    def room_of(self, xy):
        for rid in sorted(self.house.rooms):
            x0, y0, x1, y1 = self.house.rooms[rid].rect
            if x0 <= xy[0] <= x1 and y0 <= xy[1] <= y1:
                return rid
        return None

    def path(self, a, b):
        ra, rb = self.room_of(a), self.room_of(b)
        if ra == rb or ra is None or rb is None:
            return [tuple(a[:2]), tuple(b[:2])]
        way = [tuple(a[:2])]
        hubs = {"kitchen": [(6.0, 2.5)], "bedroom": [(4.5, 5.0)], "living": []}
        if ra != "living":
            way += hubs[ra]
        if rb != "living":
            way += hubs[rb]
        return way + [tuple(b[:2])]

    def resolve_place(self, name, lang=None):
        for pid, pl in self.house.places.items():
            if name in pl.name.values():
                return pid
        return None

    def resolve_object(self, name, lang=None):
        hits = [oid for oid, o in self.objects.items() if name in o.name.values()]
        return hits[0] if len(hits) == 1 else (hits or None)

    def resolve_person(self, name, lang=None):
        for pid, p in self.people.items():
            if name in p.name.values():
                return pid
        return None


def static_people(world, t=0.0):
    from homeloop_robot._hs_compat import PersonState
    return {pid: PersonState(pid, tuple(p.pos), (0.0, 0.0), world.room_of(p.pos), True)
            for pid, p in sorted(world.people.items())}


def walker(pid, start, end, speed, t_start=0.0, room_fn=None):
    """people(t) for one person walking a straight line at constant speed from t_start, then standing."""
    from homeloop_robot._hs_compat import PersonState
    L = math.dist(start, end)
    ux, uy = ((end[0] - start[0]) / L, (end[1] - start[1]) / L) if L else (0.0, 0.0)

    def people(t):
        s = min(max(0.0, t - t_start) * speed, L)
        moving = 0 < (t - t_start) * speed < L
        pos = (start[0] + ux * s, start[1] + uy * s)
        vel = (ux * speed, uy * speed) if moving else (0.0, 0.0)
        return {pid: PersonState(pid, pos, vel, room_fn(pos) if room_fn else "living", True)}
    return people


def world_available() -> bool:
    try:
        from homeloop_robot.world import from_house  # noqa: F401
        from homeloop_robot.houses import list_houses  # noqa: F401
        return True
    except ImportError:
        return False


def core_profile(name: str):
    """The core's resolved profile when the profiles package exists, else this stream's fragments."""
    try:
        from homeloop_robot.profiles import load_profile
        return load_profile(name)
    except ImportError:
        return load_params(name)


def core_available() -> bool:
    try:
        import homeloop_robot.world  # noqa: F401
        import homeloop_robot.profiles  # noqa: F401
        return hasattr(homeloop_robot.profiles, "load_profile")
    except ImportError:
        return False
