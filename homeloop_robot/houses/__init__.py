"""House layouts: ``list_houses()``, ``load_house(name)``, ``validate_house(house)`` (docs/world.md)."""

from __future__ import annotations

import functools
import itertools
from pathlib import Path

import yaml

from ..catalog import CLASSES, PLACE_TAGS, REQUIRED_PLACE_TAGS
from ..world import (Container, Door, House, ObjSpec, PersonSpec, Place, Room, dist, house_path,
                     polyline_min_distance)

HOUSE_DIR = Path(__file__).resolve().parent

# ideal-safety clearances (DESIGN 2.2 / 6.3): static people never cause a protective stop in `ideal`
APPROACH_CLEARANCE_M = 1.30
PATH_CLEARANCE_M = 1.20

PLACE_KINDS = ("surface", "container", "seat", "floor", "dock", "stand")
# the robot sets an object down at most this far from its approach pose (geometry check of `top`, not a
# calibrated value: about the horizontal reach of a mobile manipulator arm plus the base front)
TOP_MAX_FROM_POSE_M = 0.9
CONTAINER_TYPES = ("drawer", "cabinet", "fridge", "appliance", "box")
CLUTTER = ("low", "medium", "high")


def list_houses() -> list:
    return sorted(p.stem for p in HOUSE_DIR.glob("*.yaml"))


def _t(v):
    return tuple(float(x) for x in v)


def parse_house(d: dict) -> House:
    rooms = {}
    places = {}
    for rid, r in (d.get("rooms") or {}).items():
        x0, y0, x1, y1 = _t(r["rect"])
        floor = r.get("floor") or {}
        fpos = _t(floor["pos"]) if floor.get("pos") is not None else ((x0 + x1) / 2, (y0 + y1) / 2)
        rtypes = r.get("type") or []
        rooms[rid] = Room(id=rid, name=dict(r["name"]), rect=(x0, y0, x1, y1), floor_pos=fpos,
                          types=tuple([rtypes] if isinstance(rtypes, str) else rtypes))
        places[f"floor@{rid}"] = Place(id=f"floor@{rid}", room=rid, kind="floor",
                                       name={"en": "floor", "ko": "바닥"}, aliases={"en": [], "ko": []},
                                       pos=fpos, yaw_deg=0.0, height_m=0.0, clutter="high", capacity=99,
                                       tags=sorted(floor.get("tags") or []), hard_nav=False)
    doors = [Door(rooms=tuple(x["rooms"]), at=_t(x["at"]), width_m=float(x.get("width_m", 0.9)))
             for x in d.get("doors") or []]
    for pid, p in (d.get("places") or {}).items():
        c = p.get("container")
        places[pid] = Place(
            id=pid, room=p["room"], kind=p.get("kind", "surface"), name=dict(p["name"]),
            aliases={"en": list((p.get("aliases") or {}).get("en") or []),
                     "ko": list((p.get("aliases") or {}).get("ko") or [])},
            pos=_t(p["pos"]), yaw_deg=float(p.get("yaw_deg", 0.0)), height_m=float(p.get("height_m", 0.8)),
            clutter=p.get("clutter", "medium"), capacity=int(p.get("capacity", 4)),
            tags=sorted(p.get("tags") or []), hard_nav=bool(p.get("hard_nav", False)),
            container=Container(type=c["type"], openable=bool(c.get("openable", True)),
                                opened=bool(c.get("opened", False))) if c else None,
            person_pos=_t(p["person_pos"]) if p.get("person_pos") is not None else None,
            category=p.get("category"),
            top=_t(p["top"]) if p.get("top") is not None else None)
    objects = [ObjSpec(id=o["id"], cls=o["cls"], attrs=dict(o.get("attrs") or {}), at=o["at"],
                       alt=list(o.get("alt") or [])) for o in d.get("objects") or []]
    people = [PersonSpec(id=p["id"], role=p.get("role", "other"), name=dict(p["name"]),
                         age_group=str(p.get("age_group", "30-39")), sex=p.get("sex", "female"),
                         child=bool(p.get("child", False)), seat=p["seat"], pos=_t(p["pos"]),
                         alt_seats=list(p.get("alt_seats") or []),
                         aliases={"en": list((p.get("aliases") or {}).get("en") or []),
                                  "ko": list((p.get("aliases") or {}).get("ko") or [])},
                         frail=bool(p.get("frail", False)),
                         prefers_handover=bool(p.get("prefers_handover", False)),
                         walks_to=list(p.get("walks_to") or []))
              for p in d.get("people") or []]
    rb = d.get("robot") or {}
    return House(house=d["house"], version=int(d.get("version", 1)), name=dict(d.get("name") or {}),
                 rooms=rooms, doors=doors, places=places, objects=objects, people=people,
                 robot_start=rb.get("start"), dock=rb.get("dock"), raw=d)


@functools.lru_cache(maxsize=None)
def _load(name: str) -> House:
    path = HOUSE_DIR / f"{name}.yaml"
    if not path.is_file():
        raise KeyError(f"unknown house {name!r} (have {', '.join(list_houses())})")
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    if d.get("house") != name:
        raise ValueError(f"{path.name}: house: {d.get('house')!r} != file stem {name!r}")
    return parse_house(d)


def load_house(name: str) -> House:
    """The parsed house (cached; treat it as read-only)."""
    return _load(str(name))


def seat_positions(house: House) -> list:
    """(person id, seat place, body position) for every seat any person may use."""
    out = []
    for p in house.people:
        out.append((p.id, p.seat, tuple(p.pos)))
        for s in list(p.alt_seats) + list(p.walks_to):
            pl = house.places.get(s)
            if pl is not None and pl.person_pos is not None:
                out.append((p.id, s, tuple(pl.person_pos)))
    return out


def validate_house(house: House) -> list:
    """Every problem of a house as a list of strings (empty = valid). DESIGN 2.2."""
    errs = []
    E = errs.append
    rooms, places = house.rooms, house.places
    # rooms / doors
    if not rooms:
        E("no rooms")
    for d in house.doors:
        if len(d.rooms) != 2 or any(r not in rooms for r in d.rooms):
            E(f"door {d.rooms}: unknown room")
            continue
        a, b = (rooms[r] for r in d.rooms)
        if not (a.contains(d.at, 0.1) and b.contains(d.at, 0.1)):
            E(f"door {d.rooms} at {d.at}: not on the shared edge of both rooms")
    # connectivity
    if rooms:
        seen, todo = set(), [sorted(rooms)[0]]
        while todo:
            r = todo.pop()
            if r in seen:
                continue
            seen.add(r)
            todo += [x for d in house.doors if r in d.rooms for x in d.rooms]
        if seen != set(rooms):
            E(f"rooms not connected: {sorted(set(rooms) - seen)}")
    # places
    for pid, p in sorted(places.items()):
        if "@" not in pid or pid.split("@", 1)[1] != p.room:
            E(f"place {pid}: id must be <name>@<room>")
        if p.room not in rooms:
            E(f"place {pid}: unknown room {p.room}")
            continue
        if not rooms[p.room].contains(p.pos):
            E(f"place {pid}: pos {p.pos} outside room {p.room}")
        if p.kind not in PLACE_KINDS:
            E(f"place {pid}: kind {p.kind}")
        if p.clutter not in CLUTTER:
            E(f"place {pid}: clutter {p.clutter}")
        if p.kind == "container" and (p.container is None or p.container.type not in CONTAINER_TYPES):
            E(f"place {pid}: container needs a container: {{type: ...}}")
        if p.kind != "container" and p.container is not None:
            E(f"place {pid}: container block on a {p.kind}")
        bad = set(p.tags) - PLACE_TAGS
        if bad:
            E(f"place {pid}: unknown tags {sorted(bad)}")
        for lg in ("en", "ko"):
            if not p.name.get(lg):
                E(f"place {pid}: name.{lg} missing")
        if p.top is not None:
            if p.kind != "surface":
                E(f"place {pid}: top on a {p.kind} (only surfaces have a top)")
            elif not rooms[p.room].contains(p.top):
                E(f"place {pid}: top {p.top} outside room {p.room}")
            elif dist(p.top, p.pos) > TOP_MAX_FROM_POSE_M + 1e-9:
                E(f"place {pid}: top {p.top} is {dist(p.top, p.pos):.2f} m from its approach pose "
                  f"(> {TOP_MAX_FROM_POSE_M})")
        if p.kind == "stand":
            if p.person_pos is None:
                E(f"place {pid}: a stand spot needs person_pos")
            if p.capacity != 0:
                E(f"place {pid}: a stand spot holds nothing (capacity 0)")
    # objects
    ids = [o.id for o in house.objects]
    if len(ids) != len(set(ids)):
        E("duplicate object ids")
    count = {}
    for o in house.objects:
        if o.cls not in CLASSES:
            E(f"object {o.id}: unknown class {o.cls}")
        for pl in [o.at] + list(o.alt):
            if pl not in places:
                E(f"object {o.id}: unknown place {pl}")
            elif places[pl].kind in ("floor", "dock"):
                E(f"object {o.id}: place {pl} is a {places[pl].kind}")
        count[o.at] = count.get(o.at, 0) + 1
    for pl, n in count.items():
        if pl in places and n > places[pl].capacity:
            E(f"place {pl}: {n} objects > capacity {places[pl].capacity}")
    # people
    pids = [p.id for p in house.people]
    if len(pids) != len(set(pids)) or set(pids) & set(ids):
        E("duplicate person ids")
    if sum(1 for p in house.people if p.role == "user") != 1:
        E("need exactly one person with role: user")
    for p in house.people:
        for s in [p.seat] + list(p.alt_seats):
            if s not in places:
                E(f"person {p.id}: unknown seat {s}")
        for s in p.alt_seats:
            if s in places and places[s].person_pos is None:
                E(f"person {p.id}: alt seat {s} has no person_pos")
        for s in p.walks_to:
            if s not in places or places[s].kind not in ("seat", "stand") or places[s].person_pos is None:
                E(f"person {p.id}: walks_to {s} must be a seat / stand spot with person_pos")
        if not any(r.contains(p.pos) for r in rooms.values()):
            E(f"person {p.id}: pos outside every room")
    # robot
    if house.robot_start not in places or house.dock not in places:
        E("robot.start / robot.dock must be places")
    elif places[house.dock].kind != "dock":
        E(f"robot.dock {house.dock} is not a dock place")
    # ideal-safety clearances
    seats = seat_positions(house)
    for pid, p in sorted(places.items()):
        for who, seat, xy in seats:
            d = dist(p.pos, xy)
            if d < APPROACH_CLEARANCE_M - 1e-9:
                E(f"clearance: approach pose of {pid} is {d:.2f} m from {who} at {seat} (< {APPROACH_CLEARANCE_M})")
    poses = sorted(places)
    for a, b in itertools.combinations(poses, 2):
        path = house_path(house, places[a].pos, places[b].pos)
        for who, seat, xy in seats:
            d = polyline_min_distance(xy, path)
            if d < PATH_CLEARANCE_M - 1e-9:
                E(f"clearance: path {a} -> {b} passes {d:.2f} m from {who} at {seat} (< {PATH_CLEARANCE_M})")
    # content minimums
    real_places = [p for p in places.values() if p.kind != "floor"]
    if len(real_places) < 8:
        E(f"only {len(real_places)} places (< 8)")
    conts = [p for p in places.values() if p.kind == "container"]
    if len(conts) < 2 or not any(p.container.type == "drawer" for p in conts) or \
            not any(p.container.type in ("fridge", "cabinet") for p in conts):
        E("need >= 2 containers incl. a drawer and a fridge or cabinet")
    if not any(p.container.type == "appliance" for p in conts):
        E("need an appliance container (microwave)")
    if len(house.objects) < 15:
        E(f"only {len(house.objects)} objects (< 15)")
    by_cls = {}
    for o in house.objects:
        key = tuple(sorted(o.attrs.items()))
        if key in by_cls.get(o.cls, set()):
            E(f"object {o.id}: same class and attrs as another object (indistinguishable)")
        by_cls.setdefault(o.cls, set()).add(key)
    pairs = sum(1 for v in by_cls.values() if len(v) >= 2)
    if pairs < 3:
        E(f"only {pairs} confusable classes (same class, different attrs; need >= 3)")
    tags = {t for p in places.values() for t in p.tags}
    for t in REQUIRED_PLACE_TAGS:
        if t not in tags:
            E(f"no place tagged {t}")
    return errs
