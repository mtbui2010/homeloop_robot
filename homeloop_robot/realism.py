"""Robot-side realism rules (DESIGN 13; docs/realism.md): the catalog and the houses.

    R-a  catalog completeness: every object class and receptacle category has its provenance and
         attribute fields
    R-b  placement plausibility: every object's initial place and every alternative place is one of
         its class's typical receptacles
    R-c  size: an object never goes into a receptacle smaller than it; liquids are packaged
    R-d  robot ability: `graspable` agrees with the payload limit and the grasp class
    R-h  house plausibility: room types have their required fixtures; every place pair is 0.5-20 m
         apart by path; objects per house and per receptacle within plausible ranges (assumed)

``homeloop_bench`` reuses :func:`placement_ok` for goal destinations (R-b) and :func:`report` in its
``data realism`` command. ``python -m homeloop_robot.realism [--strict]`` prints the JSON report.
"""

from __future__ import annotations

import itertools
import json
import sys

from .catalog import (CLASSES, PAYLOAD_KG, PLACE_TAGS, REALISM, RECEPTACLES, REQUIRED_FIXTURES, SIZE_ORDER,
                      is_typical, place_category, size_fits)
from .world import polyline_length

ROOM_TYPES = ("living", "kitchen", "bedroom", "bathroom", "study", "balcony", "utility", "dining")
PAIR_MIN_M, PAIR_MAX_M = 0.5, 20.0
# plausible ranges (assumed: true; no published count of objects per home / per receptacle was used)
OBJECTS_PER_HOUSE = (15, 80)
OBJECTS_PER_RECEPTACLE_MAX = 12
RANGES_NOTE = ("assumed: true. A modest home inventory for a benchmark (15-80 tracked objects) and at most 12 "
               "tracked objects on / in one receptacle; no published count was used.")
EXAMPLES = 20


def _v(rule, where, why):
    return {"rule": rule, "where": where, "why": why}


# ── R-a, R-d: catalog ────────────────────────────────────────────────────────────────────────────────────

def check_catalog() -> list:
    out = []
    need = ("category", "size_class", "provenance", "mass_kg", "graspable", "liquid", "fragile", "sharp", "food",
            "hot", "typical_receptacles")
    for cls in sorted(CLASSES):
        r = REALISM.get(cls)
        if r is None:
            out.append(_v("R-a", cls, "no realism entry"))
            continue
        for f in need:
            if f not in r:
                out.append(_v("R-a", cls, f"missing {f}"))
        if r.get("size_class") not in SIZE_ORDER:
            out.append(_v("R-a", cls, f"size_class {r.get('size_class')!r}"))
        if not r.get("provenance") and not r.get("provenance_note"):
            out.append(_v("R-a", cls, "no provenance and no note why"))
        for p in r.get("provenance") or []:
            if not str(p.get("url", "")).startswith("https://"):
                out.append(_v("R-a", cls, f"provenance without a URL: {p}"))
        if not r.get("typical_receptacles"):
            out.append(_v("R-a", cls, "no typical receptacles"))
        for rec, src in sorted((r.get("typical_receptacles") or {}).items()):
            if rec not in RECEPTACLES:
                out.append(_v("R-a", cls, f"typical receptacle {rec!r} is not a known category"))
            if not (src.get("url") or (src.get("assumed") and src.get("reason"))):
                out.append(_v("R-a", cls, f"typical receptacle {rec}: no source and no assumed reason"))
        c = CLASSES[cls]
        graspable = c.grasp_class not in ("heavy", "fixed") and r.get("mass_kg", 99) <= PAYLOAD_KG
        if bool(r.get("graspable")) != graspable or c.liftable != graspable:
            out.append(_v("R-d", cls, f"graspable {r.get('graspable')} disagrees with mass {r.get('mass_kg')} kg / "
                                      f"grasp class {c.grasp_class} / payload {PAYLOAD_KG} kg"))
        if r.get("liquid") and not r.get("packaged_liquid"):
            out.append(_v("R-c", cls, "unpackaged liquid"))
    for cat, rec in sorted(RECEPTACLES.items()):
        if not rec.get("room_types"):
            out.append(_v("R-a", cat, "receptacle category without room_types"))
        if "capacity_size_class" not in rec:
            out.append(_v("R-a", cat, "receptacle category without capacity_size_class"))
        if not rec.get("thor") and not rec.get("note"):
            out.append(_v("R-a", cat, "non-AI2-THOR category without a note"))
    return out


# ── R-b, R-c: placements ─────────────────────────────────────────────────────────────────────────────────

def placement_ok(house_or_world, cls: str, pid: str) -> tuple:
    """(ok, reason): may an object of class ``cls`` plausibly be kept on / in place ``pid``? (R-b + R-c)"""
    house = house_or_world.house if hasattr(house_or_world, "objects") and hasattr(house_or_world, "robot") \
        else house_or_world
    pl = house.places.get(pid)
    if pl is None:
        return False, f"unknown place {pid}"
    if cls not in REALISM:
        return False, f"unknown class {cls}"
    cat = place_category(pl)
    if not cat:
        return False, f"{pid}: no receptacle category"
    if not is_typical(cls, cat):
        return False, f"{cls} is not typically kept on / in a {cat} ({pid})"
    if not size_fits(cls, cat):
        return False, f"{cls} (size {REALISM[cls]['size_class']}) does not fit in a {cat} ({pid})"
    if REALISM[cls]["liquid"] and not REALISM[cls]["packaged_liquid"] and pl.kind != "container":
        return False, f"{cls} is a liquid outside a container"
    return True, ""


def check_house(house) -> list:
    out = []
    name = house.house
    places = house.places
    # R-b / R-c: initial and alternative places
    for o in house.objects:
        for pid in [o.at] + list(o.alt):
            ok, why = placement_ok(house, o.cls, pid)
            if not ok:
                rule = "R-c" if "does not fit" in why or "liquid" in why else "R-b"
                out.append(_v(rule, f"{name}:{o.id}", why))
    # R-h: fixtures per room type
    for rid, room in sorted(house.rooms.items()):
        if not room.types:
            out.append(_v("R-h", f"{name}:{rid}", "room without a type"))
        for t in room.types:
            if t not in ROOM_TYPES:
                out.append(_v("R-h", f"{name}:{rid}", f"unknown room type {t}"))
            cats = {place_category(p) for p in places.values() if p.room == rid}
            for alts in REQUIRED_FIXTURES.get(t, ()):
                if not cats & set(alts):
                    out.append(_v("R-h", f"{name}:{rid}", f"a {t} needs a {' or '.join(alts)}"))
        # receptacle categories belong in this room type
    for pid, p in sorted(places.items()):
        cat = place_category(p)
        if cat not in RECEPTACLES:
            out.append(_v("R-h", f"{name}:{pid}", f"unknown receptacle category {cat!r}"))
            continue
        rt = RECEPTACLES[cat]["room_types"]
        room = house.rooms[p.room]
        if "*" not in rt and not set(room.types) & set(rt):
            out.append(_v("R-h", f"{name}:{pid}", f"a {cat} in a {'/'.join(room.types)} room"))
        if set(p.tags) - PLACE_TAGS:
            out.append(_v("R-h", f"{name}:{pid}", "unknown place tag"))
    # R-h: distances between places by path
    from .world import house_path
    for a, b in itertools.combinations(sorted(places), 2):
        d = polyline_length(house_path(house, places[a].pos, places[b].pos))
        if not (PAIR_MIN_M <= d <= PAIR_MAX_M):
            out.append(_v("R-h", f"{name}:{a}~{b}", f"{d:.2f} m apart by path (allowed {PAIR_MIN_M}-{PAIR_MAX_M})"))
    # R-h: object counts
    n = len(house.objects)
    if not (OBJECTS_PER_HOUSE[0] <= n <= OBJECTS_PER_HOUSE[1]):
        out.append(_v("R-h", name, f"{n} objects (allowed {OBJECTS_PER_HOUSE})"))
    for pid, p in sorted(places.items()):
        if p.capacity > OBJECTS_PER_RECEPTACLE_MAX and p.kind != "floor":
            out.append(_v("R-h", f"{name}:{pid}", f"capacity {p.capacity} > {OBJECTS_PER_RECEPTACLE_MAX}"))
    return out


def report(houses=None) -> dict:
    """{"ok", "rules": {rule: {"violations": n, "examples": [...]}}, "checked": {...}, "ranges_note"}."""
    from .houses import list_houses, load_house
    names = list(houses) if houses is not None else list_houses()
    viol = check_catalog()
    for h in names:
        viol += check_house(load_house(h))
    rules = {}
    for r in ("R-a", "R-b", "R-c", "R-d", "R-h"):
        vs = [v for v in viol if v["rule"] == r]
        rules[r] = {"violations": len(vs), "examples": vs[:EXAMPLES]}
    n_obj = sum(len(load_house(h).objects) for h in names)
    return {"ok": not viol, "rules": rules,
            "checked": {"classes": len(CLASSES), "receptacle_categories": len(RECEPTACLES), "houses": len(names),
                        "objects": n_obj},
            "ranges_note": RANGES_NOTE}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rep = report()
    print(json.dumps(rep, sort_keys=True, ensure_ascii=False, indent=1))
    return 1 if ("--strict" in argv and not rep["ok"]) else 0


if __name__ == "__main__":
    sys.exit(main())
