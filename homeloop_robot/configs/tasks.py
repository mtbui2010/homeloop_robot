"""robot_agent ENV of a house: ``env_for(world)``; ``ENV`` for the default house (docs/robot_agent.md)."""

from __future__ import annotations

import math

from ..world import World, from_house
from .backend import DEFAULT_HOUSE


DOCK_TASK_WORDS = ["charge", "charging", "charging station", "충전", "충전기"]


PERSON_SPOT_RADIUS_M = 1.2   # Hall's personal zone, outer edge (WALTERS05 Table 1; docs/calibration.md)

# robot_agent's AssistLoop reads a goal place that normalises to one of these words as "the user, place
# unknown" (assist_loop._USER_WORDS) and asks where they are; a person whose id is such a word ('user') is keyed
# in the ENV under a non-reserved alias (person_key) and mapped back to the id (person_target). The copy is
# checked against robot_agent's own set by the bench test tests/test_reach_ra_bind.py.
RESERVED_USER_WORDS = frozenset({"me", "user", "here", "you", "myself", "person"})


def _words(name) -> str:
    """robot_agent's name normaliser (assist_loop.words): '_' / '-' to spaces, camel case split, lower case."""
    import re
    s = str(name or "").replace("_", " ").replace("-", " ")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return " ".join(s.lower().split())


def _reserved(key: str) -> bool:
    w = _words(key)
    return w in RESERVED_USER_WORDS or any(w == f"{a} {u}" for a in ("the", "a", "an", "my", "your")
                                           for u in RESERVED_USER_WORDS)


def person_key(pid: str) -> str:
    """The ENV key of person ``pid``: the id itself, or ``person_<id>`` when the id is a reserved user word."""
    return f"person_{pid}" if _reserved(pid) else pid


def standoff_m() -> float:
    """move.person_standoff_m of the real profile (the same nominal value in every profile)."""
    from ..profiles import load_profile
    return float(load_profile("real").get("move.person_standoff_m"))


def person_target(env: dict, key: str, world=None):
    """(person id, spot place id or None) when ENV key ``key`` (or a person id / name of ``world``) names a
    person, else None. The spot is the one the ENV entry was built with, so a MoveTo / Place of the person goes
    where the ENV loc says."""
    e = (env or {}).get(key)
    if isinstance(e, dict) and e.get("person"):
        return e["person"], e.get("spot")
    if world is not None and key and world.resolve_place(key, None) is None:
        pid = world.resolve_person(key, None)
        if isinstance(pid, str):
            e = (env or {}).get(person_key(pid))
            if isinstance(e, dict) and e.get("person") == pid:
                return pid, e.get("spot")
            return pid, person_spot(world, pid)
    return None


def person_spot(world, pid: str, radius_m: float = PERSON_SPOT_RADIUS_M):
    """Where "near person ``pid``" is for a robot that sees the room: the nearest support surface (table, desk,
    counter, nightstand, shelf) in the person's room whose set-down spot is within ``radius_m`` of where they are
    now and that has free room, or None. Chosen from the same scene facts every planner observes (people_now and
    the nearby furniture); it does NOT use the judge's reach radius, height bands or posture, so the surface may
    still be out of the person's reach, and then the delivery fails like anyone's would."""
    from ..reach import is_support, surface_xy
    xy = world.person_xy(pid)
    rooms = world.rooms_of(xy)
    best = []
    for plid, pl in sorted(world.house.places.items()):
        if not is_support(pl) or pl.room not in rooms or world.free_slots(plid) <= 0:
            continue
        d = math.dist(surface_xy(pl), xy)
        if d <= radius_m + 1e-9:
            best.append((d, plid))
    return sorted(best)[0][1] if best else None


def env_for(world: World) -> dict:
    """Per place: {loc: {x, y, rz}, height, default_mode, aliases, openable} keyed by place id."""
    env = {}
    for pid, p in sorted(world.house.places.items()):
        room = world.house.rooms[p.room]
        rname, pname = room.name.get("en", ""), p.name.get("en", "")
        with_room = pname if rname.lower() in pname.lower() else f"{rname} {pname}".strip()
        aliases = [p.name.get("en", ""), p.name.get("ko", "")] + list(p.aliases.get("en") or []) + \
            list(p.aliases.get("ko") or []) + [with_room]
        if pid == world.house.dock:
            # how people name the charger in a task: "go back and charge", "충전하러 가"
            aliases += DOCK_TASK_WORDS
        if "_" in pid:
            # robot_agent reads a copied key through its word normalizer ('bath_cabinet@bathroom' ->
            # 'bath cabinet@bathroom'); this spelling resolves it back to the key instead of to the whole room
            aliases.append(pid.replace("_", " "))
        seen, al = set(), []
        for a in aliases:
            if a and a not in seen:
                seen.add(a)
                al.append(a)
        env[pid] = {"loc": {"x": float(p.pos[0]), "y": float(p.pos[1]), "rz": float(p.yaw_deg)},
                    "height": float(p.height_m), "default_mode": "front", "aliases": al,
                    "openable": bool(p.container and p.container.openable)}
    # people: robot_agent's planners name a person as the place to bring something to ("bring me the mug" ->
    # on(mug -> grandma)); the entry stands at the free support surface nearest to the person within Hall's
    # personal zone (person_spot, geometry only) and records it as ``spot``; with none, it stands where a move to
    # the person stops (skills.person_stop_xy, the robot's own rule). ra_skills.move / place of the entry go to
    # the spot (or to the person), so the robot ends at the ENV loc and robot_agent's arrival check holds.
    from ..skills import person_stop_xy
    for pid, per in sorted(world.people.items()):
        key = person_key(pid)
        if key in env:
            continue
        spot = person_spot(world, pid)
        if spot is not None:
            p = world.house.places[spot]
            loc, height = {"x": float(p.pos[0]), "y": float(p.pos[1]), "rz": float(p.yaw_deg)}, float(p.height_m)
        else:
            xy = world.person_xy(pid)
            sx, sy = person_stop_xy(world, xy, standoff_m())
            loc = {"x": float(sx), "y": float(sy), "rz": float(math.degrees(math.atan2(xy[1] - sy, xy[0] - sx)))}
            height = 0.0
        aliases, seen = [], set()
        for a in [per.name.get("en", ""), per.name.get("ko", "")] + list(per.aliases.get("en") or []) + \
                list(per.aliases.get("ko") or []) + ([key.replace("_", " ")] if key != pid else []):
            if a and a not in seen:
                seen.add(a)
                aliases.append(a)
        env[key] = {"loc": loc, "height": height, "default_mode": "front", "aliases": aliases, "openable": False,
                    "person": pid, "spot": spot}
    return env


ENV = env_for(from_house(DEFAULT_HOUSE, 0))
