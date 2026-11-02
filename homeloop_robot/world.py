"""The TRUE symbolic world: house layout, objects, people, robot state, geometry (docs/world.md).

Skills read and change this state; planners never see it (only the bench's privileged oracle does).
"""

from __future__ import annotations

import copy as _copy
import heapq
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from .catalog import CLASSES, COLORS
from .rng import Streams

LANGS = ("en", "ko")


# ── static layout ─────────────────────────────────────────────────────────────────────────────────────

@dataclass
class Room:
    id: str
    name: dict
    rect: tuple                      # x0, y0, x1, y1 (m)
    floor_pos: tuple = None          # approach pose of floor@<room> (where dropped objects are picked up)

    def contains(self, xy, tol: float = 1e-9) -> bool:
        x0, y0, x1, y1 = self.rect
        return x0 - tol <= xy[0] <= x1 + tol and y0 - tol <= xy[1] <= y1 + tol


@dataclass
class Door:
    rooms: tuple
    at: tuple
    width_m: float


@dataclass
class Container:
    type: str                        # drawer | cabinet | fridge | appliance | box
    openable: bool
    opened: bool


@dataclass
class Place:
    id: str                          # "<place>@<room>"
    room: str
    kind: str                        # surface | container | seat | floor | dock
    name: dict
    aliases: dict
    pos: tuple                       # robot approach pose (x, y)
    yaw_deg: float
    height_m: float
    clutter: str                     # low | medium | high
    capacity: int
    tags: list
    hard_nav: bool
    container: Optional[Container] = None
    person_pos: Optional[tuple] = None   # body position of a person using this place as a seat


@dataclass
class ObjSpec:
    id: str
    cls: str
    attrs: dict
    at: str
    alt: list


@dataclass
class PersonSpec:
    id: str
    role: str                        # user | other
    name: dict
    age_group: str
    sex: str
    child: bool
    seat: str
    pos: tuple
    alt_seats: list
    aliases: dict = field(default_factory=dict)
    frail: bool = False


@dataclass
class House:
    house: str
    version: int
    name: dict
    rooms: dict                      # id -> Room
    doors: list
    places: dict                     # id -> Place (incl. generated floor@<room>)
    objects: list                    # ObjSpec (YAML default arrangement)
    people: list                     # PersonSpec
    robot_start: str
    dock: str
    raw: dict = field(default_factory=dict, repr=False)


# ── dynamic state ─────────────────────────────────────────────────────────────────────────────────────

@dataclass
class Obj:
    id: str
    cls: str
    attrs: dict
    at: str                          # place id | "robot" | "person:<id>" | "floor@<room>"
    inside: bool
    alt: list


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
    alt_seats: list
    aliases: dict = field(default_factory=dict)
    frail: bool = False


@dataclass
class RobotState:
    at: Optional[str]
    pose: tuple                      # TRUE pose (x, y, yaw_deg)
    holding: Optional[str] = None
    perceived: set = field(default_factory=set)
    docked: bool = False
    estop: bool = False
    partial_open: set = field(default_factory=set)
    phantoms: set = field(default_factory=set)   # ids find reported here although they are not (false positive)


def norm(s: str) -> str:
    """Name normalisation for resolvers: NFKC, lower case, punctuation dropped, whitespace collapsed;
    Korean text also drops spaces (so "부엌 조리대" == "부엌조리대")."""
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = re.sub(r"[^\w\s@]", " ", s)
    s = re.sub(r"[_\s]+", " ", s).strip()
    if re.search(r"[가-힣]", s):
        s = s.replace(" ", "")
    return s


@dataclass
class World:
    house: House
    seed_state: int
    objects: dict                    # id -> Obj
    opened: set
    people: dict                     # id -> Person (start state)
    robot: RobotState
    faults: dict = field(default_factory=dict)          # device -> FaultState
    utterances: list = field(default_factory=list)      # Utterance
    semantic_violations: list = field(default_factory=list)   # HazardEvent
    initial_at: dict = field(default_factory=dict)

    # ── basics ────────────────────────────────────────────────────────────────────────────────────────
    def copy(self) -> "World":
        house = self.house
        self.house = None
        try:
            w = _copy.deepcopy(self)
        finally:
            self.house = house
        w.house = house                      # the static layout is shared, never mutated
        return w

    @property
    def places(self) -> dict:
        return self.house.places

    def place(self, pid: str) -> Place:
        return self.house.places[pid]

    def is_container(self, pid: str) -> bool:
        p = self.house.places.get(pid)
        return bool(p and p.kind == "container")

    def objects_at(self, pid: str) -> list:
        return sorted(o.id for o in self.objects.values() if o.at == pid)

    def visible_at(self, place_id: str) -> list:
        """Objects the camera can see at a place: on a surface, or inside an opened (not partly
        opened) container."""
        p = self.house.places.get(place_id)
        if p is None:
            return []
        if p.kind == "container":
            if place_id not in self.opened or place_id in self.robot.partial_open:
                return []
        return self.objects_at(place_id)

    def free_slots(self, pid: str) -> int:
        return self.house.places[pid].capacity - len(self.objects_at(pid))

    def room_of_place(self, pid: str) -> Optional[str]:
        if pid.startswith("person:"):
            per = self.people.get(pid.split(":", 1)[1])
            return self.room_of(per.pos) if per else None
        p = self.house.places.get(pid)
        return p.room if p else None

    def room_of_obj(self, oid: str) -> Optional[str]:
        o = self.objects[oid]
        if o.at == "robot":
            return self.room_of(self.robot.pose[:2])
        return self.room_of_place(o.at)

    # ── resolvers ───────────────────────────────────────────────────────────────────────────────────
    def _match(self, items: list, name_or_id: str, lang: Optional[str]):
        """items: [(id, [names...])] -> id | [ids] | None (exact id first, then names)."""
        if not name_or_id:
            return None
        ids = [i for i, _ in items]
        if name_or_id in ids:
            return name_or_id
        q = norm(name_or_id)
        if q in ids:
            return q
        hits = sorted({i for i, names in items if q in names})
        if not hits:
            return None
        return hits[0] if len(hits) == 1 else hits

    def object_names(self, oid: str, lang: Optional[str] = None) -> list:
        o = self.objects[oid]
        c = CLASSES[o.cls]
        out = []
        for lg in ([lang] if lang else list(LANGS)):
            base = [c.name[lg]] + list((c.aliases or {}).get(lg) or [])
            out += base
            col = o.attrs.get("color")
            if col in COLORS:
                out += [f"{COLORS[col][lg]} {b}" for b in base]
            for k, v in sorted(o.attrs.items()):
                if k not in ("color",) and isinstance(v, str) and k == "owner":
                    per = self.people.get(v)
                    if per:
                        pn = per.name.get(lg, v)
                        out += [f"{pn}'s {b}" if lg == "en" else f"{pn} {b}" for b in base]
        return [norm(x) for x in out]

    def resolve_object(self, name_or_id: str, lang: Optional[str] = None):
        items = [(oid, self.object_names(oid, lang)) for oid in sorted(self.objects)]
        return self._match(items, name_or_id, lang)

    def place_names(self, pid: str, lang: Optional[str] = None) -> list:
        p = self.house.places[pid]
        room = self.house.rooms[p.room]
        out = []
        for lg in ([lang] if lang else list(LANGS)):
            base = [p.name.get(lg, "")] + list((p.aliases or {}).get(lg) or [])
            base = [b for b in base if b]
            out += base
            rn = room.name.get(lg, "")
            out += [f"{rn} {b}" for b in base[:1]]
            if lg == "en":
                out += [f"{b} in the {rn}" for b in base[:1]]
            else:
                out += [f"{rn}의 {b}" for b in base[:1]]
        return [norm(x) for x in out]

    def resolve_place(self, name_or_id: str, lang: Optional[str] = None):
        items = [(pid, self.place_names(pid, lang)) for pid in sorted(self.house.places)]
        r = self._match(items, name_or_id, lang)
        if r is None:
            # a room name -> the room's floor place is not a target; map a room to its first non-floor
            # place is ambiguous on purpose: return the list of its places
            q = norm(name_or_id)
            for rid, room in sorted(self.house.rooms.items()):
                names = [norm(room.name.get(lg, "")) for lg in ([lang] if lang else LANGS)] + [rid]
                if q in names:
                    ps = sorted(pid for pid, p in self.house.places.items() if p.room == rid and p.kind != "floor")
                    return ps[0] if len(ps) == 1 else (ps or None)
        return r

    def person_names(self, pid: str, lang: Optional[str] = None) -> list:
        p = self.people[pid]
        out = []
        for lg in ([lang] if lang else list(LANGS)):
            out += [p.name.get(lg, "")] + list((p.aliases or {}).get(lg) or [])
        return [norm(x) for x in out if x]

    def resolve_person(self, name_or_id: str, lang: Optional[str] = None):
        if name_or_id and name_or_id.startswith("person:"):
            name_or_id = name_or_id.split(":", 1)[1]
        items = [(pid, self.person_names(pid, lang)) for pid in sorted(self.people)]
        return self._match(items, name_or_id, lang)

    def user_id(self) -> Optional[str]:
        us = sorted(p.id for p in self.people.values() if p.role == "user")
        return us[0] if us else None

    # ── geometry ────────────────────────────────────────────────────────────────────────────────────
    def room_of(self, xy) -> Optional[str]:
        for rid in sorted(self.house.rooms):
            if self.house.rooms[rid].contains(xy):
                return rid
        return None

    def rooms_of(self, xy) -> list:
        return [rid for rid in sorted(self.house.rooms) if self.house.rooms[rid].contains(xy)]

    def path(self, a, b) -> list:
        return house_path(self.house, a, b)

    def path_length(self, a, b) -> float:
        return polyline_length(self.path(a, b))

    def adjacent_rooms(self, rid: str) -> list:
        out = set()
        for d in self.house.doors:
            if rid in d.rooms:
                out |= set(d.rooms)
        out.discard(rid)
        return sorted(out)


def dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def polyline_length(pts) -> float:
    return sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def point_segment_distance(p, a, b) -> float:
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return dist(p, (ax + t * dx, ay + t * dy))


def polyline_min_distance(p, pts) -> float:
    if len(pts) == 1:
        return dist(p, pts[0])
    return min(point_segment_distance(p, pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def house_path(house: House, a, b) -> list:
    """Polyline from a to b through door centres: shortest path over the graph whose nodes are the
    doors (+ a, b) and whose edges join points in a common room (rooms are convex rectangles)."""
    a = (float(a[0]), float(a[1]))
    b = (float(b[0]), float(b[1]))
    rooms = house.rooms

    def rset(xy):
        return {rid for rid in rooms if rooms[rid].contains(xy)}

    ra, rb = rset(a), rset(b)
    if ra & rb:
        return [a, b]
    nodes = [("a", a, ra)] + [(f"d{i}", tuple(d.at), set(d.rooms)) for i, d in enumerate(house.doors)] + [("b", b, rb)]
    idx = {n[0]: k for k, n in enumerate(nodes)}
    best = {"a": 0.0}
    prev: dict = {}
    pq = [(0.0, "a")]
    done = set()
    while pq:
        d0, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        if u == "b":
            break
        _, pu, ru = nodes[idx[u]]
        for v, pv, rv in nodes:
            if v == u or v in done or not (ru & rv):
                continue
            nd = d0 + dist(pu, pv)
            if nd < best.get(v, math.inf) - 1e-12 or (abs(nd - best.get(v, math.inf)) <= 1e-12 and u < prev.get(v, "~")):
                best[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if "b" not in prev:
        return [a, b]                  # disconnected (validate_house rejects such houses)
    out = []
    cur = "b"
    while cur != "a":
        out.append(nodes[idx[cur]][1])
        cur = prev[cur]
    out.append(a)
    return [tuple(p) for p in reversed(out)]


# ── construction ──────────────────────────────────────────────────────────────────────────────────────

def from_house(name, seed_state: int = 0) -> World:
    """The world of house ``name`` (or a House) in arrangement ``seed_state``. Deterministic;
    seed_state 0 is the YAML default arrangement exactly."""
    from .houses import load_house
    house = name if isinstance(name, House) else load_house(name)
    objs = {o.id: Obj(id=o.id, cls=o.cls, attrs=dict(o.attrs), at=o.at,
                      inside=house.places[o.at].kind == "container", alt=list(o.alt)) for o in house.objects}
    people = {}
    rng = Streams(seed_state, "from_house").stream("layout") if seed_state else None
    for ps in house.people:
        seat, pos = ps.seat, tuple(ps.pos)
        if rng is not None and ps.alt_seats:
            seat = rng.choice([ps.seat] + list(ps.alt_seats))
            if seat != ps.seat:
                pos = tuple(house.places[seat].person_pos)
        people[ps.id] = Person(id=ps.id, role=ps.role, name=dict(ps.name), age_group=ps.age_group, sex=ps.sex,
                               child=ps.child, seat=seat, pos=pos, alt_seats=list(ps.alt_seats),
                               aliases=dict(ps.aliases), frail=ps.frail)
    if rng is not None:
        count = {pid: 0 for pid in house.places}
        for o in objs.values():
            count[o.at] += 1
        for oid in sorted(objs):
            o = objs[oid]
            if not o.alt or rng.random() >= 0.3:
                continue
            dest = rng.choice(sorted(o.alt))
            if count[dest] >= house.places[dest].capacity:
                continue
            count[o.at] -= 1
            count[dest] += 1
            o.at = dest
            o.inside = house.places[dest].kind == "container"
    opened = {pid for pid, p in house.places.items() if p.container and p.container.opened}
    sp = house.places[house.robot_start]
    robot = RobotState(at=house.robot_start, pose=(sp.pos[0], sp.pos[1], sp.yaw_deg),
                       docked=house.robot_start == house.dock)
    w = World(house=house, seed_state=int(seed_state), objects=objs, opened=opened, people=people, robot=robot)
    w.initial_at = {oid: o.at for oid, o in objs.items()}
    return w
